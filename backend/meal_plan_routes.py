"""Эндпоинты недельного плана питания (шаг 67)."""

from datetime import date

from fastapi import APIRouter, Depends, FastAPI, Response
from sqlalchemy.orm import Session

from access import require_same_user
from database import get_db
from error_handling import register_error_map
from meal_plan_services import (
    MealPlanNoRecipesError,
    MealPlanTargetNotReadyError,
    PlannedMealLockedError,
    PlannedMealNotFoundError,
    PlannedMealStateError,
    create_planned_meal,
    delete_planned_meal,
    generate_plan,
    get_week,
    mark_eaten,
    mark_skipped,
    reset_meal,
    update_planned_meal,
)
from schemas import (
    EatPlannedMealRequest,
    MealPlanGenerateRequest,
    MealPlanGenerateResponse,
    MealPlanWeekResponse,
    PlannedMealCreate,
    PlannedMealResponse,
    PlannedMealUpdate,
)

router = APIRouter(
    prefix="/users/{user_id}/meal-plan",
    tags=["meal-plan"],
    # Все пути ниже доступны только владельцу данных
    dependencies=[Depends(require_same_user)],
)

ERROR_RESPONSES = {
    MealPlanTargetNotReadyError: (
        409,
        "Для составления плана нужны вес и дата рождения. Заполните их в разделах «Прогресс» и «Профиль»",
    ),
    MealPlanNoRecipesError: (409, "Нет рецептов, из которых можно составить план. Добавьте рецепты"),
    PlannedMealNotFoundError: (404, "Приём пищи в плане не найден"),
    PlannedMealLockedError: (409, "Съеденный или пропущенный приём пищи нельзя менять — сначала верните его в план"),
    PlannedMealStateError: (409, "Это действие недоступно для текущего статуса приёма пищи"),
}


def register_error_handlers(app: FastAPI) -> None:
    register_error_map(app, ERROR_RESPONSES)


@router.get("", response_model=MealPlanWeekResponse)
def get_week_endpoint(user_id: int, start: date, db: Session = Depends(get_db)):
    """План питания на 7 дней с нормой и суммой плана по каждому дню.

    Запрос: GET /users/1/meal-plan?start=2026-10-26
    """
    return get_week(db, user_id, start)


@router.post("/generate", response_model=MealPlanGenerateResponse)
def generate_plan_endpoint(user_id: int, data: MealPlanGenerateRequest, db: Session = Depends(get_db)):
    """Составляет план автоматически.

    Тело: {"start": "2026-10-26", "days": 7, "overwrite": false, "batch_days": 2}
    Ответ: {"created_meals": 28, "replaced_meals": 0, "skipped_days": [], "warnings": []}
    """
    return generate_plan(db, user_id, data)


@router.post("/meals", response_model=PlannedMealResponse, status_code=201)
def create_meal_endpoint(user_id: int, data: PlannedMealCreate, db: Session = Depends(get_db)):
    """Добавляет приём пищи вручную.

    Тело (рецепт): {"planned_at": "2026-10-28T13:00:00+03:00", "meal_type": "lunch",
                    "location": "work", "recipe_id": 8, "portion_scale": 1.2}
    Тело (продукты): {"planned_at": "2026-10-28T16:00:00+03:00", "meal_type": "snack",
                      "items": [{"food_id": 5, "amount_g": 200}]}
    """
    return create_planned_meal(db, user_id, data)


@router.patch("/meals/{meal_id}", response_model=PlannedMealResponse)
def update_meal_endpoint(user_id: int, meal_id: int, data: PlannedMealUpdate, db: Session = Depends(get_db)):
    """Меняет время, место, рецепт или размер порции. Тело: {"portion_scale": 1.5, "location": "work"}."""
    return update_planned_meal(db, user_id, meal_id, data)


@router.delete("/meals/{meal_id}", status_code=204)
def delete_meal_endpoint(user_id: int, meal_id: int, db: Session = Depends(get_db)):
    """Убирает приём пищи из плана."""
    delete_planned_meal(db, user_id, meal_id)
    return Response(status_code=204)


@router.post("/meals/{meal_id}/eat", response_model=PlannedMealResponse)
def eat_meal_endpoint(
    user_id: int,
    meal_id: int,
    data: EatPlannedMealRequest | None = None,
    db: Session = Depends(get_db),
):
    """«Съел»: создаёт запись в дневнике питания. Тело необязательно: {"eaten_at": "2026-10-28T13:10:00+03:00"}."""
    return mark_eaten(db, user_id, meal_id, data or EatPlannedMealRequest())


@router.post("/meals/{meal_id}/skip", response_model=PlannedMealResponse)
def skip_meal_endpoint(user_id: int, meal_id: int, db: Session = Depends(get_db)):
    """«Пропустил»: приём пищи остаётся в плане со статусом skipped и не учитывается в сумме дня."""
    return mark_skipped(db, user_id, meal_id)


@router.post("/meals/{meal_id}/reset", response_model=PlannedMealResponse)
def reset_meal_endpoint(user_id: int, meal_id: int, db: Session = Depends(get_db)):
    """Возвращает съеденный или пропущенный приём пищи в план; созданная запись питания удаляется."""
    return reset_meal(db, user_id, meal_id)
