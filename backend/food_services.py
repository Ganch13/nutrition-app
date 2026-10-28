"""Бизнес-логика справочника продуктов (шаг 65)."""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import case, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from food_seed import BUILTIN_FOODS
from models import Food, HouseholdMember, MealEntry, RecipeIngredient, User
from visibility import can_edit, household_ids_of, source_of, visible_clause
from schemas import (
    FoodCreate,
    FoodListResponse,
    FoodNutritionResponse,
    FoodResponse,
    FoodUpdate,
    MealFromFoodCreate,
)

class FoodNotFoundError(Exception):
    # Продукта нет или он недоступен этому пользователю
    pass


class FoodReadOnlyError(Exception):
    # Встроенный продукт нельзя менять
    pass


class FoodPermissionError(Exception):
    # Продукт виден, но менять его этому пользователю нельзя
    pass


class FoodAlreadyExistsError(Exception):
    # Продукт с таким названием уже есть в той же области видимости
    pass


class FoodHouseholdAccessError(Exception):
    # Пользователь не состоит в указанном домохозяйстве
    pass


class FoodServingMissingError(Exception):
    # Просят порции, а у продукта порция не задана
    pass


class FoodMacrosError(Exception):
    # После изменения сумма белков, жиров и углеводов на 100 г превысила 100 г
    pass


class FoodInUseError(Exception):
    # Продукт входит в состав рецептов, удалить его нельзя
    pass


class FoodServingPairError(Exception):
    # Название порции и её масса должны быть заданы вместе
    pass


def normalize_search_text(value: str) -> str:
    """Приводит текст к виду для поиска: нижний регистр, «ё» → «е», лишние пробелы убраны.

    Пример: "  Творог  5% ЁЖ " → "творог 5% еж".
    Так поиск не зависит от регистра и от локали PostgreSQL.
    """
    return " ".join(value.casefold().replace("ё", "е").split())


def _money(value: Decimal) -> Decimal:
    """Округляет до сотых: Decimal("124.3333") → Decimal("124.33")."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def ensure_builtin_foods(db: Session) -> None:
    """Загружает встроенный справочник, если его в базе ещё нет.

    Вызывается перед чтением справочника. Проверка дешёвая (один запрос).
    Блокировка pg_advisory_xact_lock не даёт двум одновременным первым запросам
    загрузить справочник дважды.
    """
    exists = db.scalar(select(Food.id).where(Food.owner_user_id.is_(None), Food.household_id.is_(None)).limit(1))
    if exists is not None:
        return

    try:
        db.execute(text("SELECT pg_advisory_xact_lock(650001)"))
        # Повторная проверка уже под блокировкой: другой запрос мог успеть первым
        exists = db.scalar(
            select(Food.id).where(Food.owner_user_id.is_(None), Food.household_id.is_(None)).limit(1)
        )
        if exists is None:
            for name, category, kcal, protein, fat, carbs, serving_name, serving_grams in BUILTIN_FOODS:
                db.add(
                    Food(
                        name=name,
                        search_name=normalize_search_text(name),
                        category=category,
                        calories_per_100g=Decimal(str(kcal)),
                        protein_per_100g=Decimal(str(protein)),
                        fat_per_100g=Decimal(str(fat)),
                        carbs_per_100g=Decimal(str(carbs)),
                        serving_name=serving_name,
                        serving_grams=None if serving_grams is None else Decimal(str(serving_grams)),
                    )
                )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def _household_ids(db: Session, user_id: int) -> list[int]:
    return household_ids_of(db, user_id)


def _visible_clause(user_id: int, household_ids: list[int]):
    return visible_clause(Food, user_id, household_ids)


def _source(food: Food) -> str:
    return source_of(food)


def _can_edit(db: Session, user_id: int, food: Food) -> bool:
    return can_edit(db, user_id, food)


def to_response(db: Session, user_id: int, food: Food) -> FoodResponse:
    """Превращает строку таблицы в ответ API с признаками source и can_edit."""
    return FoodResponse(
        id=food.id,
        name=food.name,
        category=food.category,
        calories_per_100g=food.calories_per_100g,
        protein_per_100g=food.protein_per_100g,
        fat_per_100g=food.fat_per_100g,
        carbs_per_100g=food.carbs_per_100g,
        serving_name=food.serving_name,
        serving_grams=food.serving_grams,
        household_id=food.household_id,
        source=_source(food),
        can_edit=_can_edit(db, user_id, food),
    )


def list_foods(
    db: Session,
    user: User,
    query: str | None,
    category: str | None,
    limit: int,
    offset: int,
) -> FoodListResponse:
    """Ищет продукты, доступные пользователю.

    query — слова через пробел, все должны встречаться в названии: "творог 5" найдёт «Творог 5%».
    Сначала идут названия, начинающиеся с запроса, затем остальные по алфавиту.
    """
    ensure_builtin_foods(db)

    statement = select(Food).where(_visible_clause(user.id, _household_ids(db, user.id)))
    if category:
        statement = statement.where(Food.category == category)

    normalized = normalize_search_text(query) if query else ""
    for word in normalized.split():
        # Экранируем служебные символы LIKE, чтобы "%" и "_" искались как обычные
        escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(Food.search_name.like(f"%{escaped}%", escape="\\"))

    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0

    ordering = [Food.search_name.asc(), Food.id.asc()]
    if normalized:
        escaped_full = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        starts_with = case((Food.search_name.like(f"{escaped_full}%", escape="\\"), 0), else_=1)
        ordering.insert(0, starts_with)

    foods = db.scalars(statement.order_by(*ordering).limit(limit).offset(offset)).all()
    return FoodListResponse(items=[to_response(db, user.id, food) for food in foods], total=total)


def get_visible_food(db: Session, user_id: int, food_id: int) -> Food:
    """Возвращает продукт, если пользователь его видит; иначе FoodNotFoundError."""
    ensure_builtin_foods(db)
    food = db.scalar(
        select(Food).where(Food.id == food_id, _visible_clause(user_id, _household_ids(db, user_id)))
    )
    if food is None:
        raise FoodNotFoundError
    return food


def _name_taken(db: Session, name: str, owner_user_id: int, household_id: int | None, exclude_id: int | None = None) -> bool:
    """Есть ли уже продукт с таким названием в той же области (личные автора или семья)."""
    statement = select(Food.id).where(Food.search_name == normalize_search_text(name))
    if household_id is not None:
        statement = statement.where(Food.household_id == household_id)
    else:
        statement = statement.where(Food.owner_user_id == owner_user_id, Food.household_id.is_(None))
    if exclude_id is not None:
        statement = statement.where(Food.id != exclude_id)
    return db.scalar(statement.limit(1)) is not None


def create_food(db: Session, user: User, data: FoodCreate) -> FoodResponse:
    """Создаёт личный продукт или (при household_id) семейный."""
    if data.household_id is not None and db.get(HouseholdMember, (data.household_id, user.id)) is None:
        raise FoodHouseholdAccessError
    if _name_taken(db, data.name, user.id, data.household_id):
        raise FoodAlreadyExistsError

    food = Food(
        owner_user_id=user.id,
        household_id=data.household_id,
        name=data.name.strip(),
        search_name=normalize_search_text(data.name),
        category=data.category,
        calories_per_100g=data.calories_per_100g,
        protein_per_100g=data.protein_per_100g,
        fat_per_100g=data.fat_per_100g,
        carbs_per_100g=data.carbs_per_100g,
        serving_name=data.serving_name,
        serving_grams=data.serving_grams,
    )
    try:
        db.add(food)
        db.commit()
        db.refresh(food)
    except SQLAlchemyError:
        db.rollback()
        raise
    return to_response(db, user.id, food)


def _get_editable_food(db: Session, user: User, food_id: int) -> Food:
    """Находит продукт и проверяет право менять его: 404, 403 «встроенный» или 403 «нет прав»."""
    food = get_visible_food(db, user.id, food_id)
    if _source(food) == "builtin":
        raise FoodReadOnlyError
    if not _can_edit(db, user.id, food):
        raise FoodPermissionError
    return food


def update_food(db: Session, user: User, food_id: int, data: FoodUpdate) -> FoodResponse:
    """Меняет переданные поля продукта (кроме встроенных)."""
    food = _get_editable_food(db, user, food_id)
    changes = data.model_dump(exclude_unset=True)

    # Проверяем итоговые значения целиком, а не только присланные поля
    merged = {
        "calories_per_100g": food.calories_per_100g,
        "protein_per_100g": food.protein_per_100g,
        "fat_per_100g": food.fat_per_100g,
        "carbs_per_100g": food.carbs_per_100g,
        "serving_name": food.serving_name,
        "serving_grams": food.serving_grams,
        **changes,
    }
    if merged["protein_per_100g"] + merged["fat_per_100g"] + merged["carbs_per_100g"] > Decimal("100.5"):
        raise FoodMacrosError
    if (merged["serving_name"] is None) != (merged["serving_grams"] is None):
        raise FoodServingPairError

    if "name" in changes:
        if _name_taken(db, changes["name"], food.owner_user_id, food.household_id, exclude_id=food.id):
            raise FoodAlreadyExistsError
        changes["name"] = changes["name"].strip()
        food.search_name = normalize_search_text(changes["name"])

    try:
        for field, value in changes.items():
            setattr(food, field, value)
        db.commit()
        db.refresh(food)
    except SQLAlchemyError:
        db.rollback()
        raise
    return to_response(db, user.id, food)


def delete_food(db: Session, user: User, food_id: int) -> None:
    """Удаляет продукт. В записях питания остаётся снимок значений, связь food_id очищается.

    Если продукт используется в рецептах (чьих-либо), удаление запрещено: рецепт без ингредиента
    стал бы неверным. Сначала уберите продукт из рецептов.
    """
    food = _get_editable_food(db, user, food_id)
    if db.scalar(select(RecipeIngredient.id).where(RecipeIngredient.food_id == food.id).limit(1)) is not None:
        raise FoodInUseError
    try:
        db.delete(food)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def compute_nutrition(food: Food, amount_g: Decimal) -> FoodNutritionResponse:
    """Считает пищевую ценность массы amount_g.

    Пример: творог 5% (121 ккал, Б 17,2 на 100 г) и 150 г → 181,50 ккал, Б 25,80 г.
    """
    factor = amount_g / Decimal(100)
    return FoodNutritionResponse(
        food_id=food.id,
        amount_g=_money(amount_g),
        calories=_money(food.calories_per_100g * factor),
        protein_g=_money(food.protein_per_100g * factor),
        fat_g=_money(food.fat_per_100g * factor),
        carbs_g=_money(food.carbs_per_100g * factor),
    )


def resolve_amount_g(food: Food, amount_g: Decimal | None, servings: Decimal | None) -> Decimal:
    """Переводит «число порций» в граммы: 2 порции по 55 г → 110 г.

    Если передан amount_g, возвращает его. Если нужны порции, а у продукта порция не задана,
    бросает FoodServingMissingError.
    """
    if amount_g is not None:
        return amount_g
    if food.serving_grams is None:
        raise FoodServingMissingError
    return servings * food.serving_grams


def create_meal_from_food(db: Session, user_id: int, data: MealFromFoodCreate) -> MealEntry:
    """Создаёт запись приёма пищи по продукту справочника.

    Значения считаются на сервере и сохраняются как снимок (см. MealEntry.food_id).
    Описание получается вида «Яйцо куриное (сырое) — 110 г».
    """
    food = get_visible_food(db, user_id, data.food_id)
    grams = resolve_amount_g(food, data.amount_g, data.servings)
    nutrition = compute_nutrition(food, grams)

    entry = MealEntry(
        user_id=user_id,
        eaten_at=data.eaten_at,
        meal_type=data.meal_type,
        description=f"{food.name} — {nutrition.amount_g.normalize():f} г"[:250],
        calories=nutrition.calories,
        protein_g=nutrition.protein_g,
        fat_g=nutrition.fat_g,
        carbs_g=nutrition.carbs_g,
        notes=data.notes,
        food_id=food.id,
        amount_g=nutrition.amount_g,
    )
    try:
        db.add(entry)
        db.commit()
        db.refresh(entry)
    except SQLAlchemyError:
        db.rollback()
        raise
    return entry
