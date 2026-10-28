"""Бизнес-логика рецептов (шаг 67): встроенные, личные и семейные рецепты на одну порцию."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from food_services import ensure_builtin_foods, normalize_search_text
from models import Food, HouseholdMember, Recipe, RecipeIngredient, User
from recipe_seed import BUILTIN_RECIPES
from schemas import (
    RecipeCreate,
    RecipeIngredientResponse,
    RecipeListResponse,
    RecipeResponse,
    RecipeUpdate,
)
from visibility import can_edit, household_ids_of, source_of, visible_clause


class RecipeNotFoundError(Exception):
    # Рецепта нет или он недоступен этому пользователю
    pass


class RecipeReadOnlyError(Exception):
    # Встроенный рецепт нельзя менять
    pass


class RecipePermissionError(Exception):
    # Рецепт виден, но менять его этому пользователю нельзя
    pass


class RecipeAlreadyExistsError(Exception):
    # Рецепт с таким названием уже есть в той же области видимости
    pass


class RecipeHouseholdAccessError(Exception):
    # Пользователь не состоит в указанном домохозяйстве
    pass


class RecipeFoodNotFoundError(Exception):
    # Продукт из ингредиентов не найден или недоступен пользователю
    pass


class RecipeFoodNotSharedError(Exception):
    # В семейном рецепте использован личный продукт, которого не увидят остальные участники
    pass


def _money(value: Decimal) -> Decimal:
    """Округляет до сотых: Decimal("12.3456") → Decimal("12.35")."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ------------------------------------------------------------------ встроенные рецепты


def ensure_builtin_recipes(db: Session) -> None:
    """Загружает встроенные рецепты, если их ещё нет (после встроенных продуктов).

    Как и справочник продуктов, загрузка выполняется лениво при первом обращении,
    под блокировкой pg_advisory_xact_lock, чтобы два одновременных запроса не задвоили данные.
    """
    ensure_builtin_foods(db)

    def builtin_exists() -> bool:
        return (
            db.scalar(select(Recipe.id).where(Recipe.owner_user_id.is_(None), Recipe.household_id.is_(None)).limit(1))
            is not None
        )

    if builtin_exists():
        return

    try:
        db.execute(text("SELECT pg_advisory_xact_lock(650002)"))
        if not builtin_exists():
            # Название встроенного продукта → его id, например {"Банан": 71}
            food_ids = {
                name: food_id
                for food_id, name in db.execute(
                    select(Food.id, Food.name).where(Food.owner_user_id.is_(None), Food.household_id.is_(None))
                )
            }
            for name, meal_types, portable, prep_minutes, keeps_days, instructions, ingredients in BUILTIN_RECIPES:
                recipe = Recipe(
                    name=name,
                    search_name=normalize_search_text(name),
                    meal_types=meal_types,
                    portable=portable,
                    prep_minutes=prep_minutes,
                    keeps_days=keeps_days,
                    instructions=instructions,
                )
                db.add(recipe)
                db.flush()  # получаем recipe.id для ингредиентов
                for position, (food_name, grams) in enumerate(ingredients):
                    db.add(
                        RecipeIngredient(
                            recipe_id=recipe.id,
                            food_id=food_ids[food_name],
                            amount_g=Decimal(str(grams)),
                            position=position,
                        )
                    )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


# ------------------------------------------------------------------ чтение


@dataclass
class IngredientRow:
    """Ингредиент вместе с продуктом: всё нужное для расчёта и показа."""

    food: Food
    amount_g: Decimal

    def nutrition(self) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        """(ккал, белки, жиры, углеводы) этого ингредиента; 150 г творога 5% → (181.50, 25.80, 7.50, 2.70)."""
        factor = self.amount_g / Decimal(100)
        return (
            _money(self.food.calories_per_100g * factor),
            _money(self.food.protein_per_100g * factor),
            _money(self.food.fat_per_100g * factor),
            _money(self.food.carbs_per_100g * factor),
        )


def load_ingredients(db: Session, recipe_ids: list[int]) -> dict[int, list[IngredientRow]]:
    """Загружает ингредиенты нескольких рецептов одним запросом: {recipe_id: [IngredientRow, …]}."""
    result: dict[int, list[IngredientRow]] = {recipe_id: [] for recipe_id in recipe_ids}
    if not recipe_ids:
        return result
    rows = db.execute(
        select(RecipeIngredient, Food)
        .join(Food, Food.id == RecipeIngredient.food_id)
        .where(RecipeIngredient.recipe_id.in_(recipe_ids))
        .order_by(RecipeIngredient.recipe_id, RecipeIngredient.position, RecipeIngredient.id)
    ).all()
    for ingredient, food in rows:
        result[ingredient.recipe_id].append(IngredientRow(food=food, amount_g=ingredient.amount_g))
    return result


def recipe_totals(rows: list[IngredientRow]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Сумма (ккал, белки, жиры, углеводы) по ингредиентам одной порции."""
    totals = [Decimal(0)] * 4
    for row in rows:
        totals = [total + value for total, value in zip(totals, row.nutrition())]
    return totals[0], totals[1], totals[2], totals[3]


def parse_meal_types(value: str) -> list[str]:
    """"lunch,dinner" → ["lunch", "dinner"]."""
    return [item for item in value.split(",") if item]


def to_response(db: Session, user_id: int, recipe: Recipe, rows: list[IngredientRow]) -> RecipeResponse:
    """Собирает ответ API: рецепт, пищевая ценность порции и список ингредиентов."""
    calories, protein, fat, carbs = recipe_totals(rows)
    ingredients = []
    for row in rows:
        kcal, p, f, c = row.nutrition()
        ingredients.append(
            RecipeIngredientResponse(
                food_id=row.food.id,
                name=row.food.name,
                amount_g=row.amount_g,
                serving_name=row.food.serving_name,
                serving_grams=row.food.serving_grams,
                calories=kcal,
                protein_g=p,
                fat_g=f,
                carbs_g=c,
            )
        )
    return RecipeResponse(
        id=recipe.id,
        name=recipe.name,
        meal_types=parse_meal_types(recipe.meal_types),
        portable=recipe.portable,
        prep_minutes=recipe.prep_minutes,
        keeps_days=recipe.keeps_days,
        instructions=recipe.instructions,
        household_id=recipe.household_id,
        source=source_of(recipe),
        can_edit=can_edit(db, user_id, recipe),
        calories=calories,
        protein_g=protein,
        fat_g=fat,
        carbs_g=carbs,
        ingredients=ingredients,
    )


def _responses_for(db: Session, user_id: int, recipes: list[Recipe]) -> list[RecipeResponse]:
    ingredients = load_ingredients(db, [recipe.id for recipe in recipes])
    return [to_response(db, user_id, recipe, ingredients[recipe.id]) for recipe in recipes]


def list_recipes(
    db: Session,
    user: User,
    query: str | None,
    meal_type: str | None,
    portable: bool | None,
    limit: int,
    offset: int,
) -> RecipeListResponse:
    """Ищет рецепты, доступные пользователю (встроенные, свои, семейные).

    query — слова через пробел, все должны встречаться в названии: "курица греч" найдёт
    «Курица с гречкой и брокколи». meal_type — breakfast/lunch/dinner/snack.
    """
    ensure_builtin_recipes(db)
    statement = select(Recipe).where(visible_clause(Recipe, user.id, household_ids_of(db, user.id)))
    if meal_type:
        statement = statement.where(Recipe.meal_types.like(f"%{meal_type}%"))
    if portable is not None:
        statement = statement.where(Recipe.portable.is_(portable))
    for word in (normalize_search_text(query) if query else "").split():
        escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(Recipe.search_name.like(f"%{escaped}%", escape="\\"))

    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    recipes = db.scalars(statement.order_by(Recipe.search_name.asc(), Recipe.id.asc()).limit(limit).offset(offset)).all()
    return RecipeListResponse(items=_responses_for(db, user.id, list(recipes)), total=total)


def get_visible_recipe(db: Session, user_id: int, recipe_id: int) -> Recipe:
    """Возвращает рецепт, если пользователь его видит; иначе RecipeNotFoundError."""
    ensure_builtin_recipes(db)
    recipe = db.scalar(
        select(Recipe).where(Recipe.id == recipe_id, visible_clause(Recipe, user_id, household_ids_of(db, user_id)))
    )
    if recipe is None:
        raise RecipeNotFoundError
    return recipe


def get_recipe_response(db: Session, user_id: int, recipe_id: int) -> RecipeResponse:
    recipe = get_visible_recipe(db, user_id, recipe_id)
    return _responses_for(db, user_id, [recipe])[0]


def visible_recipes_with_ingredients(db: Session, user_id: int) -> list[tuple[Recipe, list[IngredientRow]]]:
    """Все рецепты пользователя вместе с ингредиентами — для автосоставления плана."""
    ensure_builtin_recipes(db)
    recipes = list(
        db.scalars(
            select(Recipe)
            .where(visible_clause(Recipe, user_id, household_ids_of(db, user_id)))
            .order_by(Recipe.id)
        ).all()
    )
    ingredients = load_ingredients(db, [recipe.id for recipe in recipes])
    return [(recipe, ingredients[recipe.id]) for recipe in recipes]


# ------------------------------------------------------------------ запись


def _name_taken(db: Session, name: str, owner_user_id: int, household_id: int | None, exclude_id: int | None = None) -> bool:
    """Есть ли уже рецепт с таким названием в той же области (личные автора или семья)."""
    statement = select(Recipe.id).where(Recipe.search_name == normalize_search_text(name))
    if household_id is not None:
        statement = statement.where(Recipe.household_id == household_id)
    else:
        statement = statement.where(Recipe.owner_user_id == owner_user_id, Recipe.household_id.is_(None))
    if exclude_id is not None:
        statement = statement.where(Recipe.id != exclude_id)
    return db.scalar(statement.limit(1)) is not None


def _resolve_foods(db: Session, user_id: int, household_id: int | None, food_ids: list[int]) -> dict[int, Food]:
    """Находит продукты ингредиентов и проверяет, что их можно использовать в этом рецепте.

    Личный рецепт: подойдут любые продукты, которые видит автор.
    Семейный рецепт: только встроенные продукты и продукты этой же семьи — личный продукт
    автора остальные участники не увидят, и рецепт бы «сломался».
    """
    ensure_builtin_foods(db)
    foods = db.scalars(
        select(Food).where(Food.id.in_(set(food_ids)), visible_clause(Food, user_id, household_ids_of(db, user_id)))
    ).all()
    by_id = {food.id: food for food in foods}
    if len(by_id) != len(set(food_ids)):
        raise RecipeFoodNotFoundError
    if household_id is not None:
        for food in foods:
            if source_of(food) == "personal":
                raise RecipeFoodNotSharedError
            if food.household_id is not None and food.household_id != household_id:
                raise RecipeFoodNotSharedError
    return by_id


def _write_ingredients(db: Session, recipe_id: int, ingredients) -> None:
    for position, item in enumerate(ingredients):
        db.add(RecipeIngredient(recipe_id=recipe_id, food_id=item.food_id, amount_g=item.amount_g, position=position))


def create_recipe(db: Session, user: User, data: RecipeCreate) -> RecipeResponse:
    """Создаёт личный рецепт или (при household_id) семейный."""
    if data.household_id is not None and db.get(HouseholdMember, (data.household_id, user.id)) is None:
        raise RecipeHouseholdAccessError
    if _name_taken(db, data.name, user.id, data.household_id):
        raise RecipeAlreadyExistsError
    _resolve_foods(db, user.id, data.household_id, [item.food_id for item in data.ingredients])

    recipe = Recipe(
        owner_user_id=user.id,
        household_id=data.household_id,
        name=data.name,
        search_name=normalize_search_text(data.name),
        meal_types=",".join(data.meal_types),
        portable=data.portable,
        prep_minutes=data.prep_minutes,
        keeps_days=data.keeps_days,
        instructions=data.instructions,
    )
    try:
        db.add(recipe)
        db.flush()
        _write_ingredients(db, recipe.id, data.ingredients)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return get_recipe_response(db, user.id, recipe.id)


def _get_editable_recipe(db: Session, user: User, recipe_id: int) -> Recipe:
    """Находит рецепт и проверяет право менять: 404, 403 «встроенный» или 403 «нет прав»."""
    recipe = get_visible_recipe(db, user.id, recipe_id)
    if source_of(recipe) == "builtin":
        raise RecipeReadOnlyError
    if not can_edit(db, user.id, recipe):
        raise RecipePermissionError
    return recipe


def update_recipe(db: Session, user: User, recipe_id: int, data: RecipeUpdate) -> RecipeResponse:
    """Меняет переданные поля рецепта; список ингредиентов, если передан, заменяется целиком."""
    recipe = _get_editable_recipe(db, user, recipe_id)
    changes = data.model_dump(exclude_unset=True)
    ingredients = data.ingredients if "ingredients" in changes else None
    changes.pop("ingredients", None)

    if "name" in changes:
        if _name_taken(db, changes["name"], recipe.owner_user_id, recipe.household_id, exclude_id=recipe.id):
            raise RecipeAlreadyExistsError
        recipe.search_name = normalize_search_text(changes["name"])
    if "meal_types" in changes:
        changes["meal_types"] = ",".join(changes["meal_types"])
    if ingredients is not None:
        _resolve_foods(db, user.id, recipe.household_id, [item.food_id for item in ingredients])

    try:
        for field, value in changes.items():
            setattr(recipe, field, value)
        if ingredients is not None:
            for old in db.scalars(select(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe.id)).all():
                db.delete(old)
            db.flush()  # сначала удаляем, иначе уникальность (recipe_id, food_id) сработает на новых строках
            _write_ingredients(db, recipe.id, ingredients)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return get_recipe_response(db, user.id, recipe.id)


def delete_recipe(db: Session, user: User, recipe_id: int) -> None:
    """Удаляет рецепт. В плане питания остаются снимки состава, связь recipe_id очищается."""
    recipe = _get_editable_recipe(db, user, recipe_id)
    try:
        db.delete(recipe)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
