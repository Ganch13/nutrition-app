"""Бизнес-логика недельного плана питания (шаг 67).

Что делает автосоставление (generate_plan) для каждого дня:
  1. берёт норму калорий и БЖУ на этот день (norms_services.compute_day_target) —
     в тренировочные дни она больше;
  2. определяет, сколько приёмов пищи нужно (настройка «приёмов пищи в день») и какую долю
     калорий приходится на каждый;
  3. по расписанию находит время подъёма и сна, рабочие часы и тренировки, расставляет
     приёмы пищи по времени и не ставит еду вплотную перед тренировкой или во время неё;
  4. если приём пищи попал на рабочие часы — выбирает только блюда, которые можно взять с собой;
  5. подбирает рецепты (до и после тренировки — с подходящим составом) и подгоняет размер
     порции так, чтобы сумма за день была близка к норме.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from food_services import get_visible_food
from models import MealEntry, PlannedMeal, PlannedMealItem, Recipe, ScheduleEvent, TrainingSession
from norms_services import compute_day_target, get_settings
from recipe_services import (
    IngredientRow,
    get_visible_recipe,
    load_ingredients,
    recipe_totals,
    visible_recipes_with_ingredients,
    parse_meal_types,
)
from schedule_services import INACTIVE_TRAINING_STATUSES, _user_timezone
from schemas import (
    DayTargetBrief,
    EatPlannedMealRequest,
    MealPlanDay,
    MealPlanGenerateRequest,
    MealPlanGenerateResponse,
    MealPlanWeekResponse,
    PlannedMealCreate,
    PlannedMealItemResponse,
    PlannedMealResponse,
    PlannedMealUpdate,
)


class MealPlanTargetNotReadyError(Exception):
    # Нельзя посчитать норму (нет веса или даты рождения), поэтому автосоставление невозможно
    pass


class MealPlanNoRecipesError(Exception):
    # Нет ни одного подходящего рецепта
    pass


class PlannedMealNotFoundError(Exception):
    # Приёма пищи нет в плане этого пользователя
    pass


class PlannedMealLockedError(Exception):
    # Съеденный или пропущенный приём пищи нельзя менять
    pass


class PlannedMealStateError(Exception):
    # Действие невозможно в текущем статусе (например, «съел» для уже съеденного)
    pass


# ------------------------------------------------------------------ слоты и время

# Сколько приёмов пищи в день → список (тип приёма, доля калорий дня). Доли в сумме дают 1.
MEAL_SLOTS: dict[int, list[tuple[str, float]]] = {
    3: [("breakfast", 0.30), ("lunch", 0.40), ("dinner", 0.30)],
    4: [("breakfast", 0.25), ("lunch", 0.35), ("snack", 0.15), ("dinner", 0.25)],
    5: [("breakfast", 0.22), ("snack", 0.08), ("lunch", 0.30), ("snack", 0.12), ("dinner", 0.28)],
    6: [("breakfast", 0.20), ("snack", 0.08), ("lunch", 0.27), ("snack", 0.12), ("dinner", 0.25), ("snack", 0.08)],
}

DEFAULT_WAKE_MIN = 7 * 60
DEFAULT_BED_MIN = 23 * 60

# Границы размера порции относительно рецепта и шаг округления
SCALE_MIN = Decimal("0.5")
SCALE_MAX = Decimal("2.0")
SCALE_STEP = Decimal("0.05")

# Только обед и ужин можно готовить «про запас» и повторять несколько дней подряд
BATCH_SLOT_TYPES = ("lunch", "dinner")

# Названия приёмов пищи для сообщений пользователю
MEAL_TYPE_NAMES = {"breakfast": "завтрак", "lunch": "обед", "dinner": "ужин", "snack": "перекус"}


@dataclass
class DayContext:
    """Распорядок дня в минутах от локальной полуночи.

    Пример: DayContext(wake=420, bed=1380, work=[(540, 1080)], training=[(1140, 1230)]) —
    подъём в 7:00, сон в 23:00, работа 9:00–18:00, тренировка 19:00–20:30.
    """

    wake: int
    bed: int
    work: list[tuple[int, int]]
    training: list[tuple[int, int]]


def _round5(minutes: float) -> int:
    """Округляет минуты до 5: 803.2 → 805."""
    return int(round(minutes / 5)) * 5


def build_day_context(day: date, events: list[ScheduleEvent], sessions: list[TrainingSession], tz: ZoneInfo) -> DayContext:
    """Собирает распорядок дня из событий расписания и тренировочных сессий.

    Подъём — окончание сна, закончившегося этим утром; отбой — начало сна, начавшегося вечером
    этого дня или ночью. Если сна нет в расписании, берём 7:00 и 23:00.
    """
    day_start = datetime.combine(day, time.min, tzinfo=tz)

    def minutes(moment: datetime) -> float:
        # Минуты от локальной полуночи дня; вычитание «настенного» времени, как его видит человек
        return (moment.astimezone(tz) - day_start).total_seconds() / 60

    wake = DEFAULT_WAKE_MIN
    bed = DEFAULT_BED_MIN
    wake_candidates = []
    bed_candidates = []
    work: list[tuple[int, int]] = []
    training: list[tuple[int, int]] = []

    def clamp_interval(start: float, end: float) -> tuple[int, int] | None:
        start, end = max(0.0, start), min(1440.0, end)
        return (int(start), int(end)) if end > start else None

    for event in events:
        start, end = minutes(event.start_at), minutes(event.end_at)
        if event.event_type == "sleep":
            if 0 < end <= 14 * 60:
                wake_candidates.append(int(end))
            if 18 * 60 <= start < 29 * 60:
                bed_candidates.append(int(start))
        elif event.event_type == "work":
            interval = clamp_interval(start, end)
            if interval:
                work.append(interval)
        elif event.event_type == "workout":
            interval = clamp_interval(start, end)
            if interval:
                training.append(interval)

    for session in sessions:
        if session.status in INACTIVE_TRAINING_STATUSES:
            continue
        interval = clamp_interval(minutes(session.start_at), minutes(session.end_at))
        if interval:
            training.append(interval)

    if wake_candidates:
        wake = max(wake_candidates)
    if bed_candidates:
        bed = min(bed_candidates)
    # Нелепый распорядок (сон короче бодрствования на 10 часов) заменяем стандартным
    if bed - wake < 10 * 60:
        wake, bed = DEFAULT_WAKE_MIN, DEFAULT_BED_MIN

    return DayContext(wake=wake, bed=bed, work=sorted(work), training=sorted(set(training)))


def plan_meal_times(slot_types: list[str], ctx: DayContext) -> list[int]:
    """Расставляет приёмы пищи по времени. Возвращает минуты от полуночи для каждого слота.

    Завтрак — через 45 минут после подъёма, ужин — за 2,5 часа до сна (но не позже 22:30),
    обед — на 45 % пути между ними, перекусы — посередине между соседними приёмами.
    Приём пищи, попавший в «окно тренировки» (за час до начала и до конца), сдвигается
    на 75 минут до тренировки или на 30 минут после неё. Между приёмами всегда не меньше часа.

    Пример: ["breakfast", "lunch", "dinner"], подъём 7:00, сон 23:00 → [465, 810, 1230]
    (7:45, 13:30, 20:30).
    """
    first = ctx.wake + 45
    last = min(ctx.bed - 150, 22 * 60 + 30)
    if last < first + 360:
        last = first + 360
    lunch = first + (last - first) * 0.45

    times: list[float | None] = []
    for slot_type in slot_types:
        times.append({"breakfast": first, "lunch": lunch, "dinner": float(last)}.get(slot_type))

    # Перекусы: посередине между ближайшими уже расставленными приёмами
    for index, value in enumerate(times):
        if value is not None:
            continue
        previous = next((times[j] for j in range(index - 1, -1, -1) if times[j] is not None), None)
        following = next((times[j] for j in range(index + 1, len(times)) if times[j] is not None), None)
        if previous is not None and following is not None:
            times[index] = (previous + following) / 2
        elif previous is not None:
            times[index] = min(previous + 150, ctx.bed - 45)
        else:
            times[index] = (following or first) - 120

    minutes = [_round5(value) for value in times]  # type: ignore[arg-type]

    # Не едим вплотную перед тренировкой и во время неё
    for train_start, train_end in ctx.training:
        for index in range(len(minutes)):
            if not (train_start - 60 < minutes[index] < train_end):
                continue
            previous_time = minutes[index - 1] if index > 0 else ctx.wake
            options = []
            before = train_start - 75
            after = train_end + 30
            if before >= previous_time + 60 and before >= ctx.wake + 15:
                options.append(before)
            if after <= ctx.bed - 60:
                options.append(after)
            if options:
                minutes[index] = _round5(min(options, key=lambda option: abs(option - minutes[index])))

    # Порядок приёмов не должен ломаться, интервал — не меньше часа
    for index in range(1, len(minutes)):
        if minutes[index] < minutes[index - 1] + 60:
            minutes[index] = minutes[index - 1] + 60
    return [min(value, 1425) for value in minutes]


def meal_role(minute: int, ctx: DayContext) -> str | None:
    """Положение приёма пищи относительно тренировки: "post" — в течение 2,5 часов после неё,
    "pre" — за 3 часа до неё, иначе None."""
    for _, train_end in ctx.training:
        if 0 <= minute - train_end <= 150:
            return "post"
    for train_start, _ in ctx.training:
        if 0 < train_start - minute <= 180:
            return "pre"
    return None


def meal_location(minute: int, ctx: DayContext) -> str:
    """"work", если время приёма пищи попадает на рабочие часы, иначе "home"."""
    for start, end in ctx.work:
        if start <= minute < end:
            return "work"
    return "home"


# ------------------------------------------------------------------ выбор рецептов


@dataclass
class RecipeOption:
    """Рецепт с готовой пищевой ценностью порции — вариант для автосоставления."""

    recipe: Recipe
    rows: list[IngredientRow]
    meal_types: set[str]
    calories: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carbs_g: Decimal


def load_options(db: Session, user_id: int) -> list[RecipeOption]:
    """Все рецепты пользователя в виде вариантов; рецепты без калорий отбрасываются."""
    options = []
    for recipe, rows in visible_recipes_with_ingredients(db, user_id):
        calories, protein, fat, carbs = recipe_totals(rows)
        if calories <= 0:
            continue
        options.append(
            RecipeOption(
                recipe=recipe,
                rows=rows,
                meal_types=set(parse_meal_types(recipe.meal_types)),
                calories=calories,
                protein_g=protein,
                fat_g=fat,
                carbs_g=carbs,
            )
        )
    return options


def clamp_scale(value: float) -> Decimal:
    """Округляет размер порции до 0,05 и ограничивает диапазоном 0,5–2,0: 1.337 → 1.35, 3.2 → 2.0."""
    stepped = (Decimal(str(value)) / SCALE_STEP).quantize(Decimal(1), rounding=ROUND_HALF_UP) * SCALE_STEP
    return min(max(stepped, SCALE_MIN), SCALE_MAX)


def profile_penalty(option: RecipeOption, role: str | None) -> float:
    """Штраф за неподходящий состав блюда перед и после тренировки.

    Перед тренировкой лучше немного жира (штраф за долю жиров выше 25 % калорий),
    после — достаточно белка (штраф, если белок даёт меньше 25 % калорий).
    """
    calories = float(option.calories)
    if role == "pre":
        return 3 * max(0.0, float(option.fat_g) * 9 / calories - 0.25)
    if role == "post":
        return 3 * max(0.0, 0.25 - float(option.protein_g) * 4 / calories)
    return 0.0


def pick_recipe(
    options: list[RecipeOption],
    *,
    slot_type: str,
    location: str,
    role: str | None,
    slot_kcal: float,
    usage: Counter,
    day_used: set[int],
    previous: tuple[RecipeOption, int] | None,
    batch_days: int,
    jitter: int,
) -> RecipeOption | None:
    """Выбирает рецепт для приёма пищи.

    Подходят рецепты нужного типа; на работе — только «с собой». Обед и ужин можно повторить
    несколько дней подряд (batch_days), если блюдо столько хранится. Иначе побеждает рецепт
    с наименьшим штрафом: за частые повторы в неделе, за размер порции, далёкий от 1, и за состав
    до/после тренировки. jitter чередует равноценные варианты, но результат всегда одинаков
    для одних и тех же данных.
    """
    candidates = [option for option in options if slot_type in option.meal_types]
    if location == "work":
        portable = [option for option in candidates if option.recipe.portable]
        candidates = portable or candidates
    if not candidates:
        return None

    if previous is not None and slot_type in BATCH_SLOT_TYPES:
        last_option, run = previous
        if (
            run < batch_days
            and last_option.recipe.keeps_days >= run + 1
            and last_option in candidates
            and last_option.recipe.id not in day_used
        ):
            return last_option

    fresh = [option for option in candidates if option.recipe.id not in day_used] or candidates

    def score(option: RecipeOption) -> float:
        scale = min(max(slot_kcal / float(option.calories), 0.5), 2.0)
        # Если порцию пришлось ограничить, отклонение от нужной калорийности тоже штрафуется
        miss = abs(slot_kcal - float(option.calories) * scale) / max(slot_kcal, 1.0)
        return (
            usage[option.recipe.id] * 1.5
            + abs(scale - 1) * 2
            + miss * 3
            + profile_penalty(option, role)
            + ((option.recipe.id * 7 + jitter * 13) % 10) / 100
        )

    return min(fresh, key=score)


def calibrate_scales(picks: list[tuple[RecipeOption, Decimal]], target_kcal: float) -> list[Decimal]:
    """Подгоняет размеры порций так, чтобы сумма калорий дня была близка к target_kcal.

    Все порции умножаются на один коэффициент (до трёх проходов), каждая порция остаётся
    в диапазоне 0,5–2,0 от рецепта. Пример: порции дают 2200 ккал при норме 2400 → ×1,09.
    """
    scales = [scale for _, scale in picks]
    for _ in range(3):
        total = sum(float(option.calories) * float(scale) for (option, _), scale in zip(picks, scales))
        if total <= 0:
            break
        factor = target_kcal / total
        if abs(factor - 1) < 0.02:
            break
        scales = [clamp_scale(float(scale) * factor) for scale in scales]
    return scales


# ------------------------------------------------------------------ состав приёма пищи


def _round_grams(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_items(rows: list[IngredientRow], scale: Decimal) -> list[PlannedMealItem]:
    """Строки состава для порции recipe × scale.

    Масса округляется до 0,1 г, пищевая ценность считается по уже округлённой массе,
    поэтому сумма строк в точности равна итогу приёма пищи.
    Пример: 150 г куриной грудки при scale 1,2 → 180 г, 203,4 ккал.
    """
    items = []
    for row in rows:
        grams = max(_round_grams(row.amount_g * scale), Decimal("0.1"))
        factor = grams / Decimal(100)
        items.append(
            PlannedMealItem(
                food_id=row.food.id,
                name=row.food.name,
                amount_g=grams,
                calories=_money(row.food.calories_per_100g * factor),
                protein_g=_money(row.food.protein_per_100g * factor),
                fat_g=_money(row.food.fat_per_100g * factor),
                carbs_g=_money(row.food.carbs_per_100g * factor),
            )
        )
    return items


def _totals(items: list[PlannedMealItem]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    return (
        sum((item.calories for item in items), Decimal(0)),
        sum((item.protein_g for item in items), Decimal(0)),
        sum((item.fat_g for item in items), Decimal(0)),
        sum((item.carbs_g for item in items), Decimal(0)),
    )


def _add_meal(
    db: Session,
    *,
    user_id: int,
    plan_date: date,
    planned_at: datetime,
    meal_type: str,
    location: str,
    recipe_id: int | None,
    title: str,
    scale: Decimal,
    items: list[PlannedMealItem],
    notes: str | None = None,
) -> PlannedMeal:
    """Создаёт приём пищи вместе со строками состава (без commit)."""
    calories, protein, fat, carbs = _totals(items)
    meal = PlannedMeal(
        user_id=user_id,
        plan_date=plan_date,
        planned_at=planned_at,
        meal_type=meal_type,
        location=location,
        status="planned",
        recipe_id=recipe_id,
        title=title[:200],
        portion_scale=scale,
        calories=calories,
        protein_g=protein,
        fat_g=fat,
        carbs_g=carbs,
        notes=notes,
    )
    db.add(meal)
    db.flush()
    for item in items:
        item.planned_meal_id = meal.id
        db.add(item)
    return meal


# ------------------------------------------------------------------ чтение недели


def _load_items(db: Session, meal_ids: list[int]) -> dict[int, list[PlannedMealItem]]:
    result: dict[int, list[PlannedMealItem]] = {meal_id: [] for meal_id in meal_ids}
    if meal_ids:
        for item in db.scalars(
            select(PlannedMealItem).where(PlannedMealItem.planned_meal_id.in_(meal_ids)).order_by(PlannedMealItem.id)
        ):
            result[item.planned_meal_id].append(item)
    return result


def to_response(meal: PlannedMeal, items: list[PlannedMealItem]) -> PlannedMealResponse:
    return PlannedMealResponse(
        id=meal.id,
        plan_date=meal.plan_date,
        planned_at=meal.planned_at,
        meal_type=meal.meal_type,
        location=meal.location,
        status=meal.status,
        recipe_id=meal.recipe_id,
        title=meal.title,
        portion_scale=meal.portion_scale,
        calories=meal.calories,
        protein_g=meal.protein_g,
        fat_g=meal.fat_g,
        carbs_g=meal.carbs_g,
        notes=meal.notes,
        meal_entry_id=meal.meal_entry_id,
        items=[
            PlannedMealItemResponse(
                food_id=item.food_id,
                name=item.name,
                amount_g=item.amount_g,
                calories=item.calories,
                protein_g=item.protein_g,
                fat_g=item.fat_g,
                carbs_g=item.carbs_g,
            )
            for item in items
        ],
    )


def get_week(db: Session, user_id: int, start: date) -> MealPlanWeekResponse:
    """Недельный план: 7 дней, начиная со start, с нормой и суммой плана за каждый день."""
    tz = _user_timezone(db, user_id)
    days = [start + timedelta(days=offset) for offset in range(7)]
    meals = db.scalars(
        select(PlannedMeal)
        .where(PlannedMeal.user_id == user_id, PlannedMeal.plan_date >= days[0], PlannedMeal.plan_date <= days[-1])
        .order_by(PlannedMeal.planned_at, PlannedMeal.id)
    ).all()
    items = _load_items(db, [meal.id for meal in meals])

    result_days = []
    week_warnings: list[str] = []
    target_ready = True
    for index, day in enumerate(days):
        target = compute_day_target(db, user_id, day)
        if index == 0:
            target_ready = target.ready
            if not target.ready:
                week_warnings = list(target.warnings)

        day_meals = [meal for meal in meals if meal.plan_date == day]
        counted = [meal for meal in day_meals if meal.status != "skipped"]
        total_kcal = sum((meal.calories for meal in counted), Decimal(0))
        warnings: list[str] = []
        if target.ready and day_meals and target.calories:
            difference = float(total_kcal) / target.calories - 1
            if difference < -0.1:
                warnings.append(f"План даёт {round(float(total_kcal))} ккал при норме {target.calories} — меньше на {round(-difference * 100)} %.")
            elif difference > 0.1:
                warnings.append(f"План даёт {round(float(total_kcal))} ккал при норме {target.calories} — больше на {round(difference * 100)} %.")

        result_days.append(
            MealPlanDay(
                date=day,
                target=DayTargetBrief(
                    ready=target.ready,
                    calories=target.calories,
                    protein_g=target.protein_g,
                    fat_g=target.fat_g,
                    carbs_g=target.carbs_g,
                    is_training_day=target.is_training_day,
                    training_minutes=target.training_minutes,
                ),
                planned_calories=total_kcal,
                planned_protein_g=sum((meal.protein_g for meal in counted), Decimal(0)),
                planned_fat_g=sum((meal.fat_g for meal in counted), Decimal(0)),
                planned_carbs_g=sum((meal.carbs_g for meal in counted), Decimal(0)),
                meals=[to_response(meal, items[meal.id]) for meal in day_meals],
                warnings=warnings,
            )
        )

    return MealPlanWeekResponse(
        start=days[0],
        end=days[-1],
        timezone=str(tz),
        target_ready=target_ready,
        warnings=week_warnings,
        days=result_days,
    )


# ------------------------------------------------------------------ автосоставление


@dataclass
class PlanUser:
    """Человек, для которого составляется план, и всё, что нужно знать о нём заранее.

    label — имя для сообщений в семейном режиме (для личного плана пустое).
    existing — уже имеющиеся приёмы пищи по дням; usage — сколько раз использован каждый рецепт;
    batch_state — какой обед или ужин и сколько дней подряд уже повторяется.
    """

    user_id: int
    label: str
    tz: ZoneInfo
    meals_per_day: int
    options: list[RecipeOption]
    events: list[ScheduleEvent]
    sessions: list[TrainingSession]
    existing: dict[date, list[PlannedMeal]]
    usage: Counter = field(default_factory=Counter)
    batch_state: dict[str, tuple[RecipeOption, int]] = field(default_factory=dict)
    created: int = 0
    replaced: int = 0
    skipped_days: list[date] = field(default_factory=list)


@dataclass
class _Slot:
    """Один приём пищи дня в работе: тип, доля калорий, время, место и выбранный рецепт."""

    slot_type: str
    share: float
    minute: int
    kcal: float = 0.0
    location: str = "home"
    role: str | None = None
    option: RecipeOption | None = None
    scale: Decimal = Decimal(1)
    shared: bool = False


@dataclass
class _DayPlan:
    user: PlanUser
    ctx: DayContext
    slots: list[_Slot]
    kcal: float


def load_plan_user(db: Session, user_id: int, label: str, days: list[date]) -> PlanUser:
    """Собирает данные человека для составления плана на days: рецепты, расписание, уже имеющийся план."""
    tz = _user_timezone(db, user_id)
    settings = get_settings(db, user_id)

    # Расписание на весь период плюс сутки по краям (сон переходит через полночь)
    range_start = datetime.combine(days[0] - timedelta(days=1), time.min, tzinfo=tz)
    range_end = datetime.combine(days[-1] + timedelta(days=2), time.min, tzinfo=tz)
    events = list(
        db.scalars(
            select(ScheduleEvent).where(
                ScheduleEvent.user_id == user_id,
                ScheduleEvent.start_at < range_end,
                ScheduleEvent.end_at > range_start,
            )
        )
    )
    sessions = list(
        db.scalars(
            select(TrainingSession).where(
                TrainingSession.user_id == user_id,
                TrainingSession.start_at < range_end,
                TrainingSession.end_at > range_start,
            )
        )
    )
    existing: dict[date, list[PlannedMeal]] = {day: [] for day in days}
    for meal in db.scalars(
        select(PlannedMeal).where(
            PlannedMeal.user_id == user_id, PlannedMeal.plan_date >= days[0], PlannedMeal.plan_date <= days[-1]
        )
    ):
        existing[meal.plan_date].append(meal)

    return PlanUser(
        user_id=user_id,
        label=label,
        tz=tz,
        meals_per_day=settings.meals_per_day,
        options=load_options(db, user_id),
        events=events,
        sessions=sessions,
        existing=existing,
    )


def _prepare_day(db: Session, user: PlanUser, day: date, overwrite: bool) -> _DayPlan | None:
    """Готовит день человека к составлению: удаляет заменяемое, считает норму, слоты и время.

    Возвращает None, если день пропущен (там уже есть план и overwrite выключен),
    нормы нет или распределять нечего.
    """
    existing = user.existing[day]
    if existing and not overwrite:
        user.skipped_days.append(day)
        for meal in existing:
            if meal.recipe_id is not None:
                user.usage[meal.recipe_id] += 1
        user.batch_state.clear()  # цепочка повторов прервалась
        return None

    # Заменяем только ещё не съеденное; съеденное и пропущенное остаётся
    kept = [meal for meal in existing if meal.status != "planned"]
    for meal in existing:
        if meal.status == "planned":
            db.delete(meal)
            user.replaced += 1
    db.flush()

    target = compute_day_target(db, user.user_id, day)
    if not target.ready or not target.calories:
        return None

    slot_defs = MEAL_SLOTS[user.meals_per_day]
    ctx = build_day_context(day, user.events, user.sessions, user.tz)
    minutes = plan_meal_times([slot_type for slot_type, _ in slot_defs], ctx)
    slots = [_Slot(slot_type, share, minute) for (slot_type, share), minute in zip(slot_defs, minutes)]

    # Слот, который уже занят съеденным или пропущенным приёмом пищи того же типа, не планируем
    for meal in kept:
        for position, slot in enumerate(slots):
            if slot.slot_type == meal.meal_type:
                del slots[position]
                break
    eaten_kcal = float(sum((meal.calories for meal in kept if meal.status == "eaten"), Decimal(0)))
    remaining_kcal = target.calories - eaten_kcal
    if not slots or remaining_kcal < 100:
        return None

    share_sum = sum(slot.share for slot in slots)
    for slot in slots:
        slot.kcal = remaining_kcal * slot.share / share_sum
        slot.location = meal_location(slot.minute, ctx)
        slot.role = meal_role(slot.minute, ctx)
    return _DayPlan(user=user, ctx=ctx, slots=slots, kcal=remaining_kcal)


def _remember_choice(user: PlanUser, slot_type: str, option: RecipeOption) -> None:
    """Учитывает выбранный рецепт: счётчик использований и длина серии повторов обеда/ужина."""
    user.usage[option.recipe.id] += 1
    if slot_type in BATCH_SLOT_TYPES:
        previous = user.batch_state.get(slot_type)
        user.batch_state[slot_type] = (option, previous[1] + 1) if previous and previous[0] is option else (option, 1)


def run_generation(
    db: Session,
    users: list[PlanUser],
    days: list[date],
    *,
    overwrite: bool,
    batch_days: int,
    shared_types: tuple[str, ...] = (),
    shared_options: list[RecipeOption] | None = None,
) -> tuple[list[str], int]:
    """Составляет план для одного или нескольких человек (одна транзакция).

    shared_types — типы приёмов пищи, которые семья ест вместе: для них рецепт выбирается один
    на всех (из shared_options — рецептов, доступных каждому), а порция подгоняется под норму
    каждого. Общий приём пищи всегда дома и во время, подходящее самому позднему из участников.
    Возвращает (предупреждения, число общих приёмов пищи).
    """
    warnings: list[str] = []
    shared_count = 0
    family_usage: Counter = Counter()
    family_batch: dict[str, tuple[RecipeOption, int]] = {}

    def prefix(user: PlanUser) -> str:
        return f"{user.label}, " if user.label else ""

    try:
        for day_index, day in enumerate(days):
            plans = [plan for user in users if (plan := _prepare_day(db, user, day, overwrite)) is not None]

            # 1. Общие приёмы пищи: один рецепт на всех, у кого этот слот свободен
            for type_number, slot_type in enumerate(shared_types):
                # Кто на работе, за общий стол не садится: ему подберём блюдо «с собой» отдельно
                involved = [
                    (plan, slot)
                    for plan in plans
                    for slot in plan.slots
                    if slot.slot_type == slot_type and slot.location != "work"
                ]
                if len(involved) < 2 or not shared_options:
                    continue
                previous = family_batch.get(slot_type)
                option = pick_recipe(
                    shared_options,
                    slot_type=slot_type,
                    location="home",
                    role=None,
                    slot_kcal=sum(slot.kcal for _, slot in involved) / len(involved),
                    usage=family_usage,
                    day_used=set(),
                    previous=previous,
                    batch_days=batch_days,
                    jitter=day_index * 5 + type_number,
                )
                if option is None:
                    continue
                family_usage[option.recipe.id] += 1
                if slot_type in BATCH_SLOT_TYPES:
                    family_batch[slot_type] = (
                        (option, previous[1] + 1) if previous and previous[0] is option else (option, 1)
                    )
                minute = max(slot.minute for _, slot in involved)
                for plan, slot in involved:
                    slot.option, slot.shared, slot.minute, slot.location = option, True, minute, "home"
                    if any(start - 60 < minute < end for start, end in plan.ctx.training):
                        warnings.append(
                            f"{day.isoformat()}: общий приём пищи «{MEAL_TYPE_NAMES[slot_type]}» "
                            f"попадает на время тренировки ({plan.user.label or 'вы'})."
                        )
                shared_count += 1

            # 2. Остальные приёмы пищи — каждому по своим рецептам; затем подгонка порций и запись
            for plan in plans:
                user = plan.user
                day_used = {slot.option.recipe.id for slot in plan.slots if slot.option is not None}
                for slot_number, slot in enumerate(plan.slots):
                    if slot.option is None:
                        slot.option = pick_recipe(
                            user.options,
                            slot_type=slot.slot_type,
                            location=slot.location,
                            role=slot.role,
                            slot_kcal=slot.kcal,
                            usage=user.usage,
                            day_used=day_used,
                            previous=user.batch_state.get(slot.slot_type),
                            batch_days=batch_days,
                            jitter=day_index * 5 + slot_number,
                        )
                        if slot.option is None:
                            warnings.append(
                                f"{day.isoformat()}: {prefix(user)}нет рецептов для приёма пищи «{MEAL_TYPE_NAMES[slot.slot_type]}»."
                            )
                            continue
                        day_used.add(slot.option.recipe.id)
                        _remember_choice(user, slot.slot_type, slot.option)
                    else:
                        # Рецепт выбран для всей семьи; для личной статистики он тоже считается
                        _remember_choice(user, slot.slot_type, slot.option)
                    slot.scale = clamp_scale(min(max(slot.kcal / float(slot.option.calories), 0.5), 2.0))

                chosen = [slot for slot in plan.slots if slot.option is not None]
                if not chosen:
                    continue
                scales = calibrate_scales([(slot.option, slot.scale) for slot in chosen], plan.kcal)  # type: ignore[misc]

                day_total = Decimal(0)
                for slot, scale in zip(chosen, scales):
                    assert slot.option is not None
                    meal = _add_meal(
                        db,
                        user_id=user.user_id,
                        plan_date=day,
                        planned_at=datetime.combine(day, time(slot.minute // 60, slot.minute % 60), tzinfo=user.tz),
                        meal_type=slot.slot_type,
                        location=slot.location,
                        recipe_id=slot.option.recipe.id,
                        title=slot.option.recipe.name,
                        scale=scale,
                        items=build_items(slot.option.rows, scale),
                    )
                    day_total += meal.calories
                    user.created += 1

                deviation = float(day_total) / plan.kcal - 1
                if abs(deviation) > 0.08:
                    warnings.append(
                        f"{day.isoformat()}: {prefix(user)}план даёт {round(float(day_total))} ккал при норме "
                        f"{round(plan.kcal)}. Добавьте свои рецепты или измените число приёмов пищи в «Нормах и целях»."
                    )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return warnings, shared_count


def generate_plan(db: Session, user_id: int, data: MealPlanGenerateRequest) -> MealPlanGenerateResponse:
    """Составляет личный план питания на data.days дней, начиная с data.start (см. описание модуля)."""
    days = [data.start + timedelta(days=offset) for offset in range(data.days)]

    if not compute_day_target(db, user_id, days[0]).ready:
        raise MealPlanTargetNotReadyError

    user = load_plan_user(db, user_id, "", days)
    if not user.options:
        raise MealPlanNoRecipesError

    warnings, _ = run_generation(db, [user], days, overwrite=data.overwrite, batch_days=data.batch_days)
    return MealPlanGenerateResponse(
        created_meals=user.created,
        replaced_meals=user.replaced,
        skipped_days=user.skipped_days,
        warnings=warnings,
    )


# ------------------------------------------------------------------ ручное редактирование


def _get_meal(db: Session, user_id: int, meal_id: int) -> PlannedMeal:
    """Приём пищи из плана пользователя; чужой считается ненайденным."""
    meal = db.scalar(select(PlannedMeal).where(PlannedMeal.id == meal_id, PlannedMeal.user_id == user_id))
    if meal is None:
        raise PlannedMealNotFoundError
    return meal


def _meal_response(db: Session, meal: PlannedMeal) -> PlannedMealResponse:
    return to_response(meal, _load_items(db, [meal.id])[meal.id])


def create_planned_meal(db: Session, user_id: int, data: PlannedMealCreate) -> PlannedMealResponse:
    """Добавляет приём пищи в план вручную: из рецепта или из набора продуктов."""
    tz = _user_timezone(db, user_id)
    planned_at = data.planned_at
    plan_date = planned_at.astimezone(tz).date()

    if data.recipe_id is not None:
        recipe = get_visible_recipe(db, user_id, data.recipe_id)
        rows = load_ingredients(db, [recipe.id])[recipe.id]
        items = build_items(rows, data.portion_scale)
        title = data.title or recipe.name
        recipe_id = recipe.id
    else:
        items = []
        for entry in data.items or []:
            food = get_visible_food(db, user_id, entry.food_id)
            items.extend(build_items([IngredientRow(food=food, amount_g=entry.amount_g)], Decimal(1)))
        title = data.title or "Из продуктов: " + ", ".join(item.name for item in items[:3])
        recipe_id = None

    try:
        meal = _add_meal(
            db,
            user_id=user_id,
            plan_date=plan_date,
            planned_at=planned_at,
            meal_type=data.meal_type,
            location=data.location,
            recipe_id=recipe_id,
            title=title,
            scale=data.portion_scale if recipe_id is not None else Decimal(1),
            items=items,
            notes=data.notes,
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return _meal_response(db, meal)


def update_planned_meal(db: Session, user_id: int, meal_id: int, data: PlannedMealUpdate) -> PlannedMealResponse:
    """Меняет время, тип, место, рецепт или размер порции ещё не съеденного приёма пищи."""
    meal = _get_meal(db, user_id, meal_id)
    if meal.status != "planned":
        raise PlannedMealLockedError
    changes = data.model_dump(exclude_unset=True)
    tz = _user_timezone(db, user_id)

    try:
        if "planned_at" in changes:
            meal.planned_at = changes["planned_at"]
            meal.plan_date = changes["planned_at"].astimezone(tz).date()
        for field in ("meal_type", "location", "notes"):
            if field in changes:
                setattr(meal, field, changes[field])

        new_recipe_id = changes.get("recipe_id", meal.recipe_id)
        new_scale = changes.get("portion_scale", meal.portion_scale)
        if "recipe_id" in changes or "portion_scale" in changes:
            old_items = list(db.scalars(select(PlannedMealItem).where(PlannedMealItem.planned_meal_id == meal.id)))
            if new_recipe_id is not None:
                # Состав пересчитывается из рецепта
                recipe = get_visible_recipe(db, user_id, new_recipe_id)
                rows = load_ingredients(db, [recipe.id])[recipe.id]
                new_items = build_items(rows, Decimal(new_scale))
                meal.title = recipe.name
                meal.recipe_id = recipe.id
            else:
                # Ручной набор продуктов: масштабируем существующие строки пропорционально
                factor = Decimal(new_scale) / meal.portion_scale
                new_items = []
                for item in old_items:
                    grams = max(_round_grams(item.amount_g * factor), Decimal("0.1"))
                    ratio = grams / item.amount_g
                    new_items.append(
                        PlannedMealItem(
                            food_id=item.food_id,
                            name=item.name,
                            amount_g=grams,
                            calories=_money(item.calories * ratio),
                            protein_g=_money(item.protein_g * ratio),
                            fat_g=_money(item.fat_g * ratio),
                            carbs_g=_money(item.carbs_g * ratio),
                        )
                    )
            for item in old_items:
                db.delete(item)
            for item in new_items:
                item.planned_meal_id = meal.id
                db.add(item)
            meal.portion_scale = Decimal(new_scale)
            meal.calories, meal.protein_g, meal.fat_g, meal.carbs_g = _totals(new_items)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(meal)
    return _meal_response(db, meal)


def delete_planned_meal(db: Session, user_id: int, meal_id: int) -> None:
    """Убирает приём пищи из плана. Запись о съеденном (MealEntry), если была, остаётся."""
    meal = _get_meal(db, user_id, meal_id)
    try:
        db.delete(meal)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def mark_eaten(db: Session, user_id: int, meal_id: int, data: EatPlannedMealRequest) -> PlannedMealResponse:
    """Отмечает приём пищи съеденным и создаёт запись в дневнике питания (MealEntry)."""
    meal = _get_meal(db, user_id, meal_id)
    if meal.status == "eaten":
        raise PlannedMealStateError
    eaten_at = data.eaten_at or datetime.now(tz=meal.planned_at.tzinfo)
    entry = MealEntry(
        user_id=user_id,
        eaten_at=eaten_at,
        meal_type=meal.meal_type,
        description=meal.title[:250],
        calories=meal.calories,
        protein_g=meal.protein_g,
        fat_g=meal.fat_g,
        carbs_g=meal.carbs_g,
        notes="Из плана питания" + (f". {meal.notes}" if meal.notes else ""),
    )
    try:
        db.add(entry)
        db.flush()
        meal.status = "eaten"
        meal.meal_entry_id = entry.id
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(meal)
    return _meal_response(db, meal)


def mark_skipped(db: Session, user_id: int, meal_id: int) -> PlannedMealResponse:
    """Отмечает приём пищи пропущенным (из статуса «в плане»)."""
    meal = _get_meal(db, user_id, meal_id)
    if meal.status != "planned":
        raise PlannedMealStateError
    meal.status = "skipped"
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(meal)
    return _meal_response(db, meal)


def reset_meal(db: Session, user_id: int, meal_id: int) -> PlannedMealResponse:
    """Возвращает съеденный или пропущенный приём пищи в статус «в плане».

    Если «съел» создало запись в дневнике питания, она удаляется.
    """
    meal = _get_meal(db, user_id, meal_id)
    if meal.status == "planned":
        raise PlannedMealStateError
    try:
        entry_id = meal.meal_entry_id
        meal.status = "planned"
        meal.meal_entry_id = None
        db.flush()
        if entry_id is not None:
            db.execute(delete(MealEntry).where(MealEntry.id == entry_id, MealEntry.user_id == user_id))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(meal)
    return _meal_response(db, meal)
