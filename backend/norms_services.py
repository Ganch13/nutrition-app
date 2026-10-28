"""Нормы питания и прогресс целей (шаг 66).

Формулы общеизвестные и приблизительные: это ориентир для планирования, а не
медицинская рекомендация. При заболеваниях, беременности, лечении и в других особых
случаях норму должен определять врач или диетолог.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models import Goal, NutritionSettings, TrainingSession, User, WeightRecord, Workout
from schemas import (
    GoalProgressResponse,
    NutritionSettingsResponse,
    NutritionSettingsUpdate,
    NutritionTargetResponse,
)

# Коэффициент суточной активности вне тренировок (умножается на основной обмен BMR).
# Тренировки считаются отдельно, поэтому коэффициенты ниже классических 1,375…1,725.
ACTIVITY_FACTORS = {"sedentary": 1.2, "light": 1.3, "moderate": 1.4, "active": 1.5}

# Энергия килограмма жировой ткани, ккал. Общепринятое округление.
KCAL_PER_KG = 7700

# Нагрузка в MET по типу блока и интенсивности (Compendium of Physical Activities, округлено)
MET_TABLE = {
    ("strength", "low"): 3.0, ("strength", "moderate"): 4.5, ("strength", "high"): 6.0,
    ("cardio", "low"): 4.0, ("cardio", "moderate"): 7.0, ("cardio", "high"): 10.0,
    ("mixed", "low"): 4.0, ("mixed", "moderate"): 6.0, ("mixed", "high"): 8.0,
    ("other", "low"): 3.0, ("other", "moderate"): 5.0, ("other", "high"): 7.0,
}
# Если у тренировки нет блоков, считаем её умеренной смешанной нагрузкой
DEFAULT_SESSION_MET = 5.0

# Белок по умолчанию, г на кг веса, в зависимости от цели
PROTEIN_PER_KG = {
    "fat_loss": 2.0,
    "muscle_gain": 1.8,
    "performance": 1.8,
    "weight_maintenance": 1.6,
    "general_health": 1.4,
}
DEFAULT_RATE = {"fat_loss": Decimal("0.5"), "muscle_gain": Decimal("0.25")}

# Нижняя граница калорий, не ниже которой автоматический расчёт не опускается
CALORIE_FLOOR = {"male": 1500, "female": 1200, "average": 1350}

# Поправка к константе формулы Миффлина–Сен-Жеора по полу
SEX_CONSTANT = {"male": 5, "female": -161, "average": -78}

# Роль цели: направление изменения веса (−1 снижение, +1 набор, 0 удержание)
GOAL_DIRECTION = {"fat_loss": -1, "muscle_gain": 1, "weight_maintenance": 0, "performance": 0, "general_health": 0}


class NormsUserNotFoundError(Exception):
    # Пользователь не найден
    pass


def _round_int(value: float | Decimal) -> int:
    """Округляет half-up до целого: 1780.5 → 1781 (а не банковское округление Python)."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_age(birth_date: date, on_date: date) -> int:
    """Полных лет на дату: родился 1992-05-17, дата 2026-10-27 → 34."""
    years = on_date.year - birth_date.year
    if (on_date.month, on_date.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def calculate_bmr(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
    """Основной обмен по формуле Миффлина–Сен-Жеора, ккал в сутки.

    Пример: мужчина, 80 кг, 180 см, 30 лет → 10·80 + 6,25·180 − 5·30 + 5 = 1780.
    sex: "male", "female" или "average" (пол не указан — среднее значение).
    """
    return 10 * weight_kg + 6.25 * height_cm - 5 * age + SEX_CONSTANT[sex]


def get_settings(db: Session, user_id: int) -> NutritionSettings:
    """Настройки пользователя; если их ещё нет, возвращает значения по умолчанию (в базу не пишет)."""
    settings = db.get(NutritionSettings, user_id)
    if settings is not None:
        return settings
    return NutritionSettings(user_id=user_id, activity_level="sedentary", meals_per_day=4)


def get_settings_response(db: Session, user_id: int) -> NutritionSettingsResponse:
    if db.get(User, user_id) is None:
        raise NormsUserNotFoundError
    return NutritionSettingsResponse.model_validate(get_settings(db, user_id))


def save_settings(db: Session, user_id: int, data: NutritionSettingsUpdate) -> NutritionSettingsResponse:
    """Создаёт или заменяет настройки пользователя (PUT)."""
    if db.get(User, user_id) is None:
        raise NormsUserNotFoundError
    settings = db.get(NutritionSettings, user_id)
    try:
        if settings is None:
            settings = NutritionSettings(user_id=user_id)
            db.add(settings)
        settings.activity_level = data.activity_level
        settings.meals_per_day = data.meals_per_day
        settings.protein_g_per_kg = data.protein_g_per_kg
        settings.calorie_override = data.calorie_override
        settings.updated_at = datetime.now(ZoneInfo("UTC"))
        db.commit()
        db.refresh(settings)
    except SQLAlchemyError:
        db.rollback()
        raise
    return NutritionSettingsResponse.model_validate(settings)


def _weight_on(db: Session, user_id: int, on_date: date) -> Decimal | None:
    """Последний известный вес на дату (запись не позже даты; если таких нет — самая ранняя запись)."""
    record = db.scalar(
        select(WeightRecord)
        .where(WeightRecord.user_id == user_id, WeightRecord.measurement_date <= on_date)
        .order_by(WeightRecord.measurement_date.desc(), WeightRecord.id.desc())
        .limit(1)
    )
    if record is None:
        record = db.scalar(
            select(WeightRecord)
            .where(WeightRecord.user_id == user_id)
            .order_by(WeightRecord.measurement_date.asc(), WeightRecord.id.asc())
            .limit(1)
        )
    return None if record is None else record.weight_kg


def _active_goal(db: Session, user_id: int) -> Goal | None:
    """Активная цель с наивысшим приоритетом (1 — высший); при равенстве — более новая."""
    return db.scalar(
        select(Goal)
        .where(Goal.user_id == user_id, Goal.status == "active")
        .order_by(Goal.priority.asc(), Goal.id.desc())
        .limit(1)
    )


@dataclass
class ExerciseEstimate:
    kcal: int
    minutes: int


def estimate_exercise(db: Session, user: User, on_date: date, weight_kg: float) -> ExerciseEstimate:
    """Оценивает затраты на тренировки дня сверх основного обмена.

    Берутся тренировки (кроме пропущенных и отменённых), начавшиеся в этот день по часовому
    поясу пользователя. Для каждого блока: (MET − 1) × вес × часы. Единица вычитается,
    потому что один MET уже входит в основной обмен. Блоки суперсета идут одновременно,
    поэтому время каждого делится на число блоков группы, чтобы не считать его дважды.
    У тренировки без блоков берётся длительность сессии и умеренная нагрузка.
    """
    tz = ZoneInfo(user.timezone or "UTC")
    day_start = datetime.combine(on_date, datetime.min.time(), tzinfo=tz)
    day_end = day_start + timedelta(days=1)

    sessions = db.scalars(
        select(TrainingSession).where(
            TrainingSession.user_id == user.id,
            TrainingSession.start_at >= day_start,
            TrainingSession.start_at < day_end,
            TrainingSession.status.in_(("planned", "completed")),
        )
    ).all()

    total_kcal = 0.0
    total_minutes = 0.0
    for session in sessions:
        blocks = db.scalars(select(Workout).where(Workout.training_session_id == session.id)).all()
        if not blocks:
            hours = (session.end_at - session.start_at).total_seconds() / 3600
            total_kcal += (DEFAULT_SESSION_MET - 1) * weight_kg * hours
            total_minutes += hours * 60
            continue

        group_sizes: dict[int, int] = {}
        for block in blocks:
            if block.superset_group is not None:
                group_sizes[block.superset_group] = group_sizes.get(block.superset_group, 0) + 1

        for block in blocks:
            intensity = block.actual_intensity or block.planned_intensity
            met = MET_TABLE.get((block.load_type, intensity), DEFAULT_SESSION_MET)
            share = group_sizes.get(block.superset_group, 1) if block.superset_group is not None else 1
            hours = (block.end_at - block.start_at).total_seconds() / 3600 / share
            total_kcal += (met - 1) * weight_kg * hours
            total_minutes += hours * 60

    return ExerciseEstimate(kcal=_round_int(total_kcal), minutes=_round_int(total_minutes))


def compute_day_target(db: Session, user_id: int, on_date: date) -> NutritionTargetResponse:
    """Считает норму питания на день.

    Шаги: основной обмен (BMR) → × активность → + тренировки дня = расход (TDEE) →
    поправка на цель (дефицит или профицит) → распределение на белки, жиры, углеводы.
    """
    user = db.get(User, user_id)
    if user is None:
        raise NormsUserNotFoundError

    settings = get_settings(db, user_id)
    missing: list[str] = []
    warnings: list[str] = []

    weight = _weight_on(db, user_id, on_date)
    if weight is None:
        missing.append("weight")
        warnings.append("Добавьте хотя бы одно измерение веса (раздел «Прогресс»).")

    if user.birth_date is not None:
        age: int | None = calculate_age(user.birth_date, on_date)
    elif user.age is not None:
        age = user.age
    else:
        age = None
        missing.append("birth_date")
        warnings.append("Укажите дату рождения в профиле.")

    if missing:
        return NutritionTargetResponse(date=on_date, ready=False, missing=missing, warnings=warnings)

    sex = user.sex if user.sex in ("male", "female") else "average"
    if sex == "average":
        warnings.append("Пол не указан в профиле, поэтому использовано среднее значение формулы.")

    weight_kg = float(weight)
    bmr = calculate_bmr(weight_kg, user.height_cm, age, sex)
    factor = ACTIVITY_FACTORS[settings.activity_level]
    base = bmr * factor
    exercise = estimate_exercise(db, user, on_date, weight_kg)
    tdee = base + exercise.kcal

    explanation = [
        f"Основной обмен (формула Миффлина–Сен-Жеора): {_round_int(bmr)} ккал.",
        f"Повседневная активность ×{factor}: {_round_int(base)} ккал.",
    ]
    if exercise.kcal > 0:
        explanation.append(f"Тренировки дня ({exercise.minutes} мин): +{exercise.kcal} ккал.")
    else:
        explanation.append("Тренировок в этот день нет.")
    explanation.append(f"Расход за день: {_round_int(tdee)} ккал.")

    # Цель и поправка
    goal = _active_goal(db, user_id)
    goal_type = goal.goal_type if goal else None
    adjustment = 0.0
    if goal is not None:
        direction = GOAL_DIRECTION[goal.goal_type]
        reached = (
            goal.target_weight_kg is not None
            and ((direction < 0 and weight <= goal.target_weight_kg) or (direction > 0 and weight >= goal.target_weight_kg))
        )
        if direction != 0 and not reached:
            rate = goal.desired_rate_kg_per_week or DEFAULT_RATE[goal.goal_type]
            adjustment = direction * float(rate) * KCAL_PER_KG / 7
            # Ограничения безопасности: дефицит не больше 25 % расхода, профицит не больше 500 ккал
            if direction < 0 and -adjustment > 0.25 * tdee:
                adjustment = -0.25 * tdee
                warnings.append("Желаемый темп снижения слишком быстрый: дефицит ограничен 25 % от расхода.")
            if direction > 0 and adjustment > 500:
                adjustment = 500
                warnings.append("Желаемый темп набора слишком быстрый: профицит ограничен +500 ккал.")
        elif reached:
            warnings.append("Целевой вес достигнут: норма рассчитана на поддержание веса.")

    if adjustment:
        sign = "+" if adjustment > 0 else "−"
        explanation.append(f"Поправка на цель: {sign}{abs(_round_int(adjustment))} ккал.")

    calories = tdee + adjustment
    floor = CALORIE_FLOOR[sex]
    if settings.calorie_override is not None:
        calories = float(settings.calorie_override)
        explanation.append(f"Вы задали калорийность вручную: {settings.calorie_override} ккал.")
    elif calories < floor:
        calories = float(floor)
        warnings.append(f"Расчёт опустился ниже безопасного минимума, поэтому взято {floor} ккал.")

    # Макронутриенты
    protein_per_kg = float(settings.protein_g_per_kg) if settings.protein_g_per_kg else PROTEIN_PER_KG.get(goal_type, 1.6)
    protein = protein_per_kg * weight_kg
    # Белок не должен занимать больше 35 % калорий (важно при большом весе)
    protein = min(protein, 0.35 * calories / 4)
    fat = max(0.25 * calories / 9, 0.8 * weight_kg)
    carbs = (calories - protein * 4 - fat * 9) / 4
    if carbs < 50:
        # Углеводов остаётся слишком мало: уменьшаем жиры до минимума, затем фиксируем 50 г
        fat = max(0.8 * weight_kg, (calories - protein * 4 - 200) / 9)
        carbs = max(50.0, (calories - protein * 4 - fat * 9) / 4)
        warnings.append("Калорий мало для выбранного количества белка: углеводов получилось немного.")

    explanation.append(
        f"Белок {protein_per_kg:g} г/кг ≈ {_round_int(protein)} г, жиры ≈ 25 % калорий, остальное — углеводы."
    )

    return NutritionTargetResponse(
        date=on_date,
        ready=True,
        missing=[],
        warnings=warnings,
        weight_kg=weight,
        age=age,
        sex_used=sex,
        bmr=_round_int(bmr),
        base_kcal=_round_int(base),
        exercise_kcal=exercise.kcal,
        tdee=_round_int(tdee),
        goal_type=goal_type,
        goal_adjustment_kcal=_round_int(adjustment),
        calories=_round_int(calories),
        protein_g=_round_int(protein),
        fat_g=_round_int(fat),
        carbs_g=_round_int(carbs),
        # Клетчатка 14 г на 1000 ккал, вода 30 мл на кг веса — общие ориентиры
        fiber_g=_round_int(calories / 1000 * 14),
        water_ml=_round_int(weight_kg * 30 / 50) * 50,
        is_training_day=exercise.minutes > 0,
        training_minutes=exercise.minutes,
        explanation=explanation,
    )


# ---------------------------------------------------------------- прогресс цели


def _slope_per_week(points: list[tuple[date, Decimal]]) -> Decimal | None:
    """Наклон линии тренда веса, кг в неделю (метод наименьших квадратов).

    Пример: точки (1 окт, 100,0), (8 окт, 99,5), (15 окт, 99,0) → −0,5.
    Нужно минимум две точки, разнесённые не меньше чем на 7 дней, иначе None.
    """
    if len(points) < 2:
        return None
    first_day = points[0][0]
    xs = [Decimal((day - first_day).days) for day, _ in points]
    ys = [weight for _, weight in points]
    if xs[-1] - xs[0] < 7:
        return None
    n = Decimal(len(points))
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return None
    slope_per_day = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
    return slope_per_day * 7


def compute_goal_progress(db: Session, user_id: int, today: date) -> list[GoalProgressResponse]:
    """Прогресс по каждой активной цели.

    Старт — измерение ближайшее к дате начала цели (не позже; если такого нет — первое после).
    Текущий вес — последнее измерение. Темп — тренд за последние 28 дней или, если измерений мало,
    средний за весь срок цели.
    """
    if db.get(User, user_id) is None:
        raise NormsUserNotFoundError

    goals = db.scalars(
        select(Goal)
        .where(Goal.user_id == user_id, Goal.status == "active")
        .order_by(Goal.priority.asc(), Goal.id.asc())
    ).all()
    records = db.scalars(
        select(WeightRecord)
        .where(WeightRecord.user_id == user_id)
        .order_by(WeightRecord.measurement_date.asc(), WeightRecord.id.asc())
    ).all()

    results: list[GoalProgressResponse] = []
    for goal in goals:
        results.append(_progress_for_goal(goal, records, today))
    return results


def _progress_for_goal(goal: Goal, records: list[WeightRecord], today: date) -> GoalProgressResponse:
    base = dict(
        goal_id=goal.id,
        goal_type=goal.goal_type,
        target_weight_kg=goal.target_weight_kg,
        desired_rate_kg_per_week=goal.desired_rate_kg_per_week,
        target_date=goal.target_date,
    )

    def empty(message: str) -> GoalProgressResponse:
        return GoalProgressResponse(
            **base, start_weight_kg=None, current_weight_kg=None, change_kg=None, remaining_kg=None,
            progress_percent=None, actual_rate_kg_per_week=None, status="no_data", eta_date=None, message=message,
        )

    if not records:
        return empty("Нет измерений веса. Добавьте вес в разделе «Прогресс».")

    before = [r for r in records if r.measurement_date <= goal.start_date]
    start_record = before[-1] if before else records[0]
    current_record = records[-1]
    start_w, current_w = start_record.weight_kg, current_record.weight_kg
    change = current_w - start_w

    # Направление движения к цели: по целевому весу, иначе по типу цели
    direction = GOAL_DIRECTION.get(goal.goal_type, 0)
    if goal.target_weight_kg is not None:
        if goal.target_weight_kg < start_w:
            direction = -1
        elif goal.target_weight_kg > start_w:
            direction = 1
        else:
            direction = 0

    # Темп: тренд по последним 28 дням либо средний
    recent = [(r.measurement_date, r.weight_kg) for r in records if (today - r.measurement_date).days <= 28]
    rate = _slope_per_week(recent)
    if rate is None:
        elapsed_days = (current_record.measurement_date - start_record.measurement_date).days
        if elapsed_days >= 7:
            rate = change / Decimal(elapsed_days) * 7
    rate_q = None if rate is None else rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    remaining = None
    percent = None
    reached = False
    if goal.target_weight_kg is not None:
        remaining = goal.target_weight_kg - current_w
        total = goal.target_weight_kg - start_w
        reached = (direction < 0 and current_w <= goal.target_weight_kg) or (direction > 0 and current_w >= goal.target_weight_kg)
        if reached:
            percent = 100
        elif total != 0:
            percent = max(0, min(100, _round_int(change / total * 100)))
        else:
            percent = 100 if current_w == goal.target_weight_kg else 0

    desired = goal.desired_rate_kg_per_week

    def finish(status: str, message: str, eta: date | None = None) -> GoalProgressResponse:
        return GoalProgressResponse(
            **base,
            start_weight_kg=start_w,
            current_weight_kg=current_w,
            change_kg=change,
            remaining_kg=remaining,
            progress_percent=percent,
            actual_rate_kg_per_week=rate_q,
            status=status,
            eta_date=eta,
            message=message,
        )

    if reached:
        return finish("reached", "Целевой вес достигнут. Можно перейти на поддержание.")
    if rate is None:
        return finish("no_data", "Данных для оценки темпа пока мало: нужны измерения хотя бы за 7 дней.")

    # Скорость движения В СТОРОНУ цели (положительная — движемся правильно)
    toward = rate * direction
    if direction == 0:
        status = "on_track" if abs(rate) <= Decimal("0.25") else "slower"
        return finish(status, "Вес держится стабильно." if status == "on_track" else "Вес заметно меняется — проверьте питание.")
    if toward <= Decimal("-0.05"):
        return finish("wrong_direction", "Вес меняется в обратную сторону от цели. Стоит пересмотреть питание и нагрузку.")
    if toward < Decimal("0.05"):
        return finish("stalled", "Вес почти не меняется. Нужно больше времени или корректировка плана.")

    eta = None
    if remaining is not None:
        weeks = abs(remaining) / toward
        if weeks <= 520:
            eta = today + timedelta(days=int(weeks * 7))

    if desired is None:
        return finish("on_track", "Вес движется к цели.", eta)
    if toward >= desired * Decimal("1.25"):
        return finish("faster", "Темп выше желаемого. Слишком быстрое изменение веса может быть вредным.", eta)
    if toward >= desired * Decimal("0.75"):
        return finish("on_track", "Темп соответствует желаемому.", eta)
    return finish("slower", "Темп ниже желаемого. Чтобы ускорить, проверьте калорийность и регулярность записей.", eta)
