"""Список закупок и план готовки на основе недельного плана питания (шаги 68 и 69).

Личный список строится по плану одного человека, семейный (шаг 69) — по планам всех участников,
включивших «Планировать вместе»: продукты складываются, отметки «куплено» общие для семьи.
"""

import math
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from food_services import normalize_search_text
from models import Food, PlannedMeal, PlannedMealItem, Recipe, ShoppingCheck, User
from schedule_services import _user_timezone
from schemas import (
    CookingIngredient,
    CookingMealRef,
    CookingPlanResponse,
    CookingSessionResponse,
    ShoppingCheckRequest,
    ShoppingItemResponse,
    ShoppingListResponse,
)

# Порядок категорий в списке — примерно как отделы в магазине
CATEGORY_ORDER = [
    "vegetables", "fruits", "meat", "fish", "eggs", "dairy", "bakery", "grains", "legumes",
    "nuts", "fats", "sauces", "sweets", "drinks", "supplements", "other",
]

# Сколько минут добавляется к времени рецепта на каждую следующую порцию при готовке «про запас»
EXTRA_PORTION_MINUTES = 5


def scope_key_for(user_id: int) -> str:
    """Область личного списка: пользователь 5 → "u:5"."""
    return f"u:{user_id}"


def household_scope_key(household_id: int) -> str:
    """Область семейного списка: домохозяйство 3 → "h:3"."""
    return f"h:{household_id}"


def _item_key(food_id: int | None, name: str) -> str:
    """Ключ строки списка: "food:12" или, если продукт удалён из справочника, "name:хлеб"."""
    return f"food:{food_id}" if food_id is not None else f"name:{normalize_search_text(name)}"[:100]


def _ceil_grams(value: Decimal) -> Decimal:
    """Округляет вверх до целого грамма: 213.4 → 214 (покупать меньше нужного нельзя)."""
    return value.quantize(Decimal(1), rounding=ROUND_CEILING)


def _planned_items(db: Session, user_ids: list[int], start: date, end: date):
    """Строки состава приёмов пищи «в плане» за период у перечисленных людей.

    Результат: список (PlannedMeal, PlannedMealItem, Food|None).
    """
    return db.execute(
        select(PlannedMeal, PlannedMealItem, Food)
        .join(PlannedMealItem, PlannedMealItem.planned_meal_id == PlannedMeal.id)
        .outerjoin(Food, Food.id == PlannedMealItem.food_id)
        .where(
            PlannedMeal.user_id.in_(user_ids),
            PlannedMeal.plan_date >= start,
            PlannedMeal.plan_date <= end,
            PlannedMeal.status == "planned",
        )
        .order_by(PlannedMeal.planned_at, PlannedMeal.id, PlannedMealItem.id)
    ).all()


def build_shopping_list(db: Session, user_id: int, start: date, days: int) -> ShoppingListResponse:
    """Личный список закупок на период по плану одного человека."""
    _user_timezone(db, user_id)  # проверяем, что пользователь существует
    return _shopping_list(db, [user_id], None, scope_key_for(user_id), start, days)


def build_household_shopping_list(
    db: Session, household_id: int, names: dict[int, str], start: date, days: int
) -> ShoppingListResponse:
    """Семейный список закупок: names — {id участника: имя} тех, кто планирует вместе.

    Пример: names={1: "Даня", 2: "Леся"} → гречка 70 г (Даня) + 60 г (Леся) = одна строка «130 г».
    """
    return _shopping_list(db, list(names), names, household_scope_key(household_id), start, days)


def _shopping_list(
    db: Session, user_ids: list[int], names: dict[int, str] | None, scope: str, start: date, days: int
) -> ShoppingListResponse:
    """Суммирует продукты всех запланированных приёмов пищи за период.

    Пример: в трёх блюдах нужна гречка 70 + 70 + 105 г → одна строка «Гречка (сухая) — 245 г».
    Съеденные и пропущенные приёмы пищи не учитываются. names задан только для семейного списка.
    """
    end = start + timedelta(days=days - 1)
    rows = _planned_items(db, user_ids, start, end)

    totals: dict[str, Decimal] = defaultdict(Decimal)
    names_by_key: dict[str, str] = {}
    foods: dict[str, Food | None] = {}
    used_in: dict[str, list[str]] = defaultdict(list)
    eaters: dict[str, set[int]] = defaultdict(set)
    meal_ids: set[int] = set()

    for meal, item, food in rows:
        meal_ids.add(meal.id)
        key = _item_key(item.food_id, item.name)
        totals[key] += item.amount_g
        names_by_key.setdefault(key, food.name if food is not None else item.name)
        foods.setdefault(key, food)
        eaters[key].add(meal.user_id)
        if meal.title not in used_in[key]:
            used_in[key].append(meal.title)

    # Отметки «куплено»: ключ продукта → кто отметил
    checks = dict(
        db.execute(
            select(ShoppingCheck.item_key, ShoppingCheck.checked_by_user_id).where(
                ShoppingCheck.scope_key == scope, ShoppingCheck.range_start == start
            )
        ).all()
    )
    checker_names: dict[int, str] = {}
    if names is not None and checks:
        checker_names = dict(names)
        missing = {user_id for user_id in checks.values() if user_id not in checker_names}
        if missing:  # отметил тот, кто потом отключил общий план
            checker_names.update(db.execute(select(User.id, User.name).where(User.id.in_(missing))).all())

    items = []
    for key, total in totals.items():
        food = foods[key]
        grams = _ceil_grams(total)
        servings = None
        if food is not None and food.serving_grams:
            servings = (total / food.serving_grams).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        items.append(
            ShoppingItemResponse(
                key=key,
                food_id=food.id if food is not None else None,
                name=names_by_key[key],
                category=food.category if food is not None else "other",
                amount_g=grams,
                serving_name=food.serving_name if food is not None else None,
                serving_grams=food.serving_grams if food is not None else None,
                servings=servings,
                used_in=used_in[key][:5],
                checked=key in checks,
                members=[name for user_id, name in (names or {}).items() if user_id in eaters[key]],
                checked_by=checker_names.get(checks[key]) if key in checks else None,
            )
        )

    def sort_key(item: ShoppingItemResponse):
        index = CATEGORY_ORDER.index(item.category) if item.category in CATEGORY_ORDER else len(CATEGORY_ORDER)
        return index, normalize_search_text(item.name)

    items.sort(key=sort_key)
    return ShoppingListResponse(
        start=start,
        end=end,
        items=items,
        checked_count=sum(1 for item in items if item.checked),
        meals_count=len(meal_ids),
        members=list((names or {}).values()),
    )


def set_check(db: Session, user_id: int, data: ShoppingCheckRequest) -> None:
    """Ставит или снимает отметку «куплено» в личном списке (повторный вызов безопасен)."""
    _set_check(db, scope_key_for(user_id), user_id, data)


def set_household_check(db: Session, household_id: int, by_user_id: int, data: ShoppingCheckRequest) -> None:
    """То же для семейного списка; by_user_id — кто отметил (его имя видно остальным)."""
    _set_check(db, household_scope_key(household_id), by_user_id, data)


def _set_check(db: Session, scope: str, by_user_id: int, data: ShoppingCheckRequest) -> None:
    existing = db.scalar(
        select(ShoppingCheck).where(
            ShoppingCheck.scope_key == scope,
            ShoppingCheck.range_start == data.start,
            ShoppingCheck.item_key == data.key,
        )
    )
    try:
        if data.checked and existing is None:
            db.add(
                ShoppingCheck(
                    scope_key=scope, range_start=data.start, item_key=data.key, checked_by_user_id=by_user_id
                )
            )
        elif not data.checked and existing is not None:
            db.delete(existing)
        db.commit()
    except IntegrityError:
        # Два одинаковых запроса пришли одновременно: отметка уже есть — это и нужно
        db.rollback()
    except SQLAlchemyError:
        db.rollback()
        raise


def clear_checks(db: Session, user_id: int, start: date) -> None:
    """Снимает все отметки «куплено» личного списка для периода, начинающегося со start."""
    _clear_checks(db, scope_key_for(user_id), start)


def clear_household_checks(db: Session, household_id: int, start: date) -> None:
    """Снимает все отметки семейного списка."""
    _clear_checks(db, household_scope_key(household_id), start)


def _clear_checks(db: Session, scope: str, start: date) -> None:
    try:
        db.execute(delete(ShoppingCheck).where(ShoppingCheck.scope_key == scope, ShoppingCheck.range_start == start))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


# ------------------------------------------------------------------ план готовки


def build_cooking_plan(db: Session, user_id: int, start: date, days: int) -> CookingPlanResponse:
    """План готовки по личному плану питания."""
    return _cooking_plan(db, [user_id], None, _user_timezone(db, user_id), start, days)


def build_household_cooking_plan(
    db: Session, names: dict[int, str], tz: ZoneInfo, start: date, days: int
) -> CookingPlanResponse:
    """Семейный план готовки: одно блюдо для нескольких человек готовится одним подходом.

    Пример: общий ужин Дани и Леси в понедельник → одна сессия «Куриное рагу», порции 1.2 + 0.9 = 2.1.
    tz — часовой пояс того, кто смотрит план (по нему определяется «утро»).
    """
    return _cooking_plan(db, list(names), names, tz, start, days)


def _cooking_plan(
    db: Session, user_ids: list[int], names: dict[int, str] | None, tz: ZoneInfo, start: date, days: int
) -> CookingPlanResponse:
    """Группирует блюда недели в «подходы» к плите.

    Приёмы пищи с одним рецептом объединяются, если блюдо ещё не испортилось: рецепт хранится
    keeps_days дней, считая день приготовления. Если первый приём пищи до полудня и блюдо
    хранится хотя бы 2 дня, готовить советуем накануне вечером, иначе — в день первого приёма.

    Пример: куриное рагу (хранится 3 дня) в плане на пн, вт и ср → один подход в пн на 3 порции.
    """
    end = start + timedelta(days=days - 1)
    rows = _planned_items(db, user_ids, start, end)

    meals: dict[int, PlannedMeal] = {}
    items_by_meal: dict[int, list[PlannedMealItem]] = defaultdict(list)
    for meal, item, _ in rows:
        meals[meal.id] = meal
        items_by_meal[meal.id].append(item)

    # Блюда без рецепта (набор продуктов, удалённый рецепт) не готовятся — их не группируем
    by_recipe: dict[int, list[PlannedMeal]] = defaultdict(list)
    for meal in sorted(meals.values(), key=lambda m: (m.planned_at, m.id)):
        if meal.recipe_id is not None:
            by_recipe[meal.recipe_id].append(meal)

    recipes = {
        recipe.id: recipe
        for recipe in db.scalars(select(Recipe).where(Recipe.id.in_(list(by_recipe) or [0])))
    }

    sessions: list[CookingSessionResponse] = []
    for recipe_id, recipe_meals in by_recipe.items():
        recipe = recipes.get(recipe_id)
        if recipe is None:
            continue
        clusters: list[tuple[date, str, list[PlannedMeal]]] = []
        for meal in recipe_meals:
            if clusters and (meal.plan_date - clusters[-1][0]).days < recipe.keeps_days:
                clusters[-1][2].append(meal)
                continue
            morning = meal.planned_at.astimezone(tz).hour < 12
            if recipe.keeps_days >= 2 and morning:
                clusters.append((meal.plan_date - timedelta(days=1), "evening_before", [meal]))
            else:
                clusters.append((meal.plan_date, "same_day", [meal]))

        for cook_date, cook_when, cluster in clusters:
            portions = sum((meal.portion_scale for meal in cluster), Decimal(0))
            totals: dict[str, Decimal] = defaultdict(Decimal)
            for meal in cluster:
                for item in items_by_meal[meal.id]:
                    totals[item.name] += item.amount_g
            sessions.append(
                CookingSessionResponse(
                    recipe_id=recipe.id,
                    recipe_name=recipe.name,
                    cook_date=cook_date,
                    cook_when=cook_when,  # type: ignore[arg-type]
                    portions=portions,
                    estimated_minutes=recipe.prep_minutes + EXTRA_PORTION_MINUTES * (math.ceil(portions) - 1),
                    keeps_days=recipe.keeps_days,
                    instructions=recipe.instructions,
                    meals=[
                        CookingMealRef(
                            id=meal.id,
                            plan_date=meal.plan_date,
                            meal_type=meal.meal_type,
                            planned_at=meal.planned_at,
                            location=meal.location,
                            portion_scale=meal.portion_scale,
                            user_id=meal.user_id if names is not None else None,
                            user_name=names.get(meal.user_id) if names is not None else None,
                        )
                        for meal in cluster
                    ],
                    ingredients=[
                        CookingIngredient(name=name, amount_g=_ceil_grams(total)) for name, total in totals.items()
                    ],
                )
            )

    sessions.sort(key=lambda s: (s.cook_date, s.meals[0].planned_at))
    return CookingPlanResponse(
        start=start,
        end=end,
        sessions=sessions,
        total_minutes=sum(session.estimated_minutes for session in sessions),
    )
