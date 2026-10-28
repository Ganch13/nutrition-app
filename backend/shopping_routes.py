"""Эндпоинты списка закупок и плана готовки (шаг 68)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from access import require_same_user
from database import get_db
from schemas import CookingPlanResponse, ShoppingCheckRequest, ShoppingListResponse
from shopping_services import build_cooking_plan, build_shopping_list, clear_checks, set_check

router = APIRouter(
    prefix="/users/{user_id}",
    tags=["shopping"],
    # Все пути ниже доступны только владельцу данных
    dependencies=[Depends(require_same_user)],
)


@router.get("/shopping-list", response_model=ShoppingListResponse)
def shopping_list_endpoint(
    user_id: int,
    start: date,
    days: Annotated[int, Query(ge=1, le=14)] = 7,
    db: Session = Depends(get_db),
):
    """Список закупок на период: продукты всех запланированных приёмов пищи, сложенные вместе.

    Запрос: GET /users/1/shopping-list?start=2026-10-26&days=7
    Ответ: {"start": "2026-10-26", "end": "2026-11-01", "meals_count": 26, "checked_count": 1,
            "items": [{"key": "food:12", "name": "Банан", "category": "fruits", "amount_g": "480",
                       "serving_name": "1 шт. (без кожуры)", "servings": "4.0",
                       "used_in": ["Творог с бананом"], "checked": false}]}
    """
    return build_shopping_list(db, user_id, start, days)


@router.put("/shopping-list/checks", status_code=204)
def set_check_endpoint(user_id: int, data: ShoppingCheckRequest, db: Session = Depends(get_db)):
    """Ставит или снимает отметку «куплено». Тело: {"start": "2026-10-26", "key": "food:12", "checked": true}."""
    set_check(db, user_id, data)
    return Response(status_code=204)


@router.delete("/shopping-list/checks", status_code=204)
def clear_checks_endpoint(user_id: int, start: date, db: Session = Depends(get_db)):
    """Снимает все отметки периода: DELETE /users/1/shopping-list/checks?start=2026-10-26."""
    clear_checks(db, user_id, start)
    return Response(status_code=204)


@router.get("/cooking-plan", response_model=CookingPlanResponse)
def cooking_plan_endpoint(
    user_id: int,
    start: date,
    days: Annotated[int, Query(ge=1, le=14)] = 7,
    db: Session = Depends(get_db),
):
    """План готовки: что и в какой день готовить, сколько порций и сколько это займёт времени.

    Запрос: GET /users/1/cooking-plan?start=2026-10-26&days=7
    """
    return build_cooking_plan(db, user_id, start, days)
