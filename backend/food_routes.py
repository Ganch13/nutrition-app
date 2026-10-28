"""Эндпоинты справочника продуктов (шаг 65)."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Response
from sqlalchemy.orm import Session

from access import require_same_user
from database import get_db
from error_handling import register_error_map
from food_services import (
    FoodAlreadyExistsError,
    FoodHouseholdAccessError,
    FoodInUseError,
    FoodMacrosError,
    FoodNotFoundError,
    FoodPermissionError,
    FoodReadOnlyError,
    FoodServingMissingError,
    FoodServingPairError,
    compute_nutrition,
    create_food,
    create_meal_from_food,
    delete_food,
    get_visible_food,
    list_foods,
    resolve_amount_g,
    update_food,
)
from models import User
from schemas import (
    FoodCategory,
    FoodCreate,
    FoodListResponse,
    FoodNutritionResponse,
    FoodResponse,
    FoodUpdate,
    MealEntryResponse,
    MealFromFoodCreate,
)
from security import get_current_user

router = APIRouter(tags=["foods"])

ERROR_RESPONSES = {
    FoodNotFoundError: (404, "Продукт не найден"),
    FoodReadOnlyError: (403, "Встроенные продукты изменить нельзя. Создайте свой продукт на их основе"),
    FoodPermissionError: (403, "Недостаточно прав для изменения этого продукта"),
    FoodAlreadyExistsError: (409, "Продукт с таким названием уже есть"),
    FoodHouseholdAccessError: (403, "Вы не состоите в этом домохозяйстве"),
    FoodServingMissingError: (422, "У продукта не задана порция. Укажите массу в граммах"),
    FoodMacrosError: (422, "Сумма белков, жиров и углеводов на 100 г не может превышать 100 г"),
    FoodServingPairError: (422, "Название порции и её масса задаются вместе"),
    FoodInUseError: (409, "Продукт используется в рецептах. Сначала уберите его из рецептов"),
}


def register_error_handlers(app: FastAPI) -> None:
    register_error_map(app, ERROR_RESPONSES)


@router.get("/foods", response_model=FoodListResponse)
def list_foods_endpoint(
    q: Annotated[str | None, Query(max_length=100)] = None,
    category: FoodCategory | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Поиск по справочнику: встроенные, свои и семейные продукты.

    Запрос: GET /foods?q=творог&category=dairy&limit=20
    Ответ: {"items": [{"id": 21, "name": "Творог 5%", "calories_per_100g": "121.00", ...,
            "source": "builtin", "can_edit": false}], "total": 3}
    """
    return list_foods(db, current_user, q, category, limit, offset)


@router.post("/foods", response_model=FoodResponse, status_code=201)
def create_food_endpoint(
    data: FoodCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Добавляет свой продукт (или семейный, если указан household_id)."""
    return create_food(db, current_user, data)


@router.patch("/foods/{food_id}", response_model=FoodResponse)
def update_food_endpoint(
    food_id: int,
    data: FoodUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Меняет свой продукт. Пример тела: {"calories_per_100g": 125}."""
    return update_food(db, current_user, food_id, data)


@router.delete("/foods/{food_id}", status_code=204)
def delete_food_endpoint(
    food_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Удаляет свой продукт. Уже сделанные записи питания сохраняются."""
    delete_food(db, current_user, food_id)
    return Response(status_code=204)


@router.get("/foods/{food_id}/nutrition", response_model=FoodNutritionResponse)
def food_nutrition_endpoint(
    food_id: int,
    amount_g: Annotated[Decimal | None, Query(gt=0, le=10000)] = None,
    servings: Annotated[Decimal | None, Query(gt=0, le=100)] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Считает КБЖУ для массы или числа порций.

    GET /foods/14/nutrition?amount_g=150   или   GET /foods/14/nutrition?servings=2
    """
    if (amount_g is None) == (servings is None):
        raise HTTPException(status_code=422, detail="Укажите либо amount_g, либо servings")
    food = get_visible_food(db, current_user.id, food_id)
    return compute_nutrition(food, resolve_amount_g(food, amount_g, servings))


@router.post(
    "/users/{user_id}/meal-entries/from-food",
    response_model=MealEntryResponse,
    status_code=201,
    dependencies=[Depends(require_same_user)],
)
def create_meal_from_food_endpoint(
    user_id: int,
    data: MealFromFoodCreate,
    db: Session = Depends(get_db),
):
    """Добавляет приём пищи из справочника; калории и БЖУ считает сервер.

    Пример тела: {"food_id": 14, "amount_g": 150, "eaten_at": "2026-10-27T08:30:00+03:00",
                  "meal_type": "breakfast"}
    """
    return create_meal_from_food(db, user_id, data)
