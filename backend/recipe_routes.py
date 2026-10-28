"""Эндпоинты рецептов (шаг 67)."""

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Query, Response
from sqlalchemy.orm import Session

from database import get_db
from error_handling import register_error_map
from models import User
from recipe_services import (
    RecipeAlreadyExistsError,
    RecipeFoodNotFoundError,
    RecipeFoodNotSharedError,
    RecipeHouseholdAccessError,
    RecipeNotFoundError,
    RecipePermissionError,
    RecipeReadOnlyError,
    create_recipe,
    delete_recipe,
    get_recipe_response,
    list_recipes,
    update_recipe,
)
from schemas import PlanMealType, RecipeCreate, RecipeListResponse, RecipeResponse, RecipeUpdate
from security import get_current_user

router = APIRouter(tags=["recipes"])

ERROR_RESPONSES = {
    RecipeNotFoundError: (404, "Рецепт не найден"),
    RecipeReadOnlyError: (403, "Встроенные рецепты изменить нельзя. Создайте свой рецепт на их основе"),
    RecipePermissionError: (403, "Недостаточно прав для изменения этого рецепта"),
    RecipeAlreadyExistsError: (409, "Рецепт с таким названием уже есть"),
    RecipeHouseholdAccessError: (403, "Вы не состоите в этом домохозяйстве"),
    RecipeFoodNotFoundError: (422, "Один из продуктов в составе не найден или вам недоступен"),
    RecipeFoodNotSharedError: (
        422,
        "В семейном рецепте можно использовать только встроенные и семейные продукты. "
        "Сделайте нужный продукт семейным",
    ),
}


def register_error_handlers(app: FastAPI) -> None:
    register_error_map(app, ERROR_RESPONSES)


@router.get("/recipes", response_model=RecipeListResponse)
def list_recipes_endpoint(
    q: Annotated[str | None, Query(max_length=100)] = None,
    meal_type: PlanMealType | None = None,
    portable: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Поиск рецептов: встроенные, свои и семейные.

    Запрос: GET /recipes?q=курица&meal_type=lunch&portable=true
    Ответ: {"items": [{"id": 8, "name": "Курица с гречкой и брокколи", "meal_types": ["lunch", "dinner"],
            "portable": true, "calories": "510.00", "protein_g": "48.00", ..., "ingredients": [...],
            "source": "builtin", "can_edit": false}], "total": 1}
    """
    return list_recipes(db, current_user, q, meal_type, portable, limit, offset)


@router.get("/recipes/{recipe_id}", response_model=RecipeResponse)
def get_recipe_endpoint(
    recipe_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Один рецепт с ингредиентами: GET /recipes/8."""
    return get_recipe_response(db, current_user.id, recipe_id)


@router.post("/recipes", response_model=RecipeResponse, status_code=201)
def create_recipe_endpoint(
    data: RecipeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Создаёт свой рецепт (с household_id — семейный).

    Тело: {"name": "Омлет с сыром", "meal_types": ["breakfast"], "portable": false, "prep_minutes": 10,
           "keeps_days": 1, "ingredients": [{"food_id": 17, "amount_g": 165}, {"food_id": 27, "amount_g": 20}]}
    """
    return create_recipe(db, current_user, data)


@router.patch("/recipes/{recipe_id}", response_model=RecipeResponse)
def update_recipe_endpoint(
    recipe_id: int,
    data: RecipeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Меняет свой рецепт. Тело: {"portable": true, "ingredients": [{"food_id": 17, "amount_g": 200}]}."""
    return update_recipe(db, current_user, recipe_id, data)


@router.delete("/recipes/{recipe_id}", status_code=204)
def delete_recipe_endpoint(
    recipe_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Удаляет свой рецепт. Уже составленные планы сохраняются."""
    delete_recipe(db, current_user, recipe_id)
    return Response(status_code=204)
