"""Эндпоинты семейного планирования (шаг 69): общий план, закупки и готовка домохозяйства."""

from datetime import date
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, FastAPI, Query, Response
from sqlalchemy.orm import Session

from access import require_household_member
from database import get_db
from error_handling import register_error_map
from family_services import (
    FamilyPlanningNotEnoughMembersError,
    FamilyPlanningNotJoinedError,
    generate_family_plan,
    get_family_week,
    get_planning_state,
    set_my_planning,
    together_members,
)
from models import User
from schemas import (
    CookingPlanResponse,
    FamilyPlanGenerateRequest,
    FamilyPlanGenerateResponse,
    FamilyPlanningState,
    FamilyPlanningUpdate,
    FamilyPlanWeekResponse,
    ShoppingCheckRequest,
    ShoppingListResponse,
)
from security import get_current_user
from shopping_services import (
    build_household_cooking_plan,
    build_household_shopping_list,
    clear_household_checks,
    set_household_check,
)


def _require_member(household_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Пускает только участников этого домохозяйства (404 — семьи нет, 403 — вы не участник)."""
    require_household_member(household_id, db, current_user)


router = APIRouter(
    prefix="/households/{household_id}",
    tags=["family-planning"],
    dependencies=[Depends(_require_member)],
)

ERROR_RESPONSES = {
    FamilyPlanningNotJoinedError: (
        403,
        "Чтобы видеть общий план, включите у себя «Планировать вместе». Свои данные вы открываете сами",
    ),
    FamilyPlanningNotEnoughMembersError: (
        409,
        "Для общего плана нужны минимум двое участников, которые включили «Планировать вместе» "
        "и заполнили вес и дату рождения",
    ),
}


def register_error_handlers(app: FastAPI) -> None:
    register_error_map(app, ERROR_RESPONSES)


@router.get("/planning", response_model=FamilyPlanningState)
def planning_state_endpoint(
    household_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Кто из семьи включил «Планировать вместе». Запрос: GET /households/1/planning."""
    return get_planning_state(db, household_id, current_user.id)


@router.put("/planning/me", response_model=FamilyPlanningState)
def set_my_planning_endpoint(
    household_id: int,
    data: FamilyPlanningUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Включает или выключает ваше участие в общем плане. Тело: {"plans_together": true}."""
    return set_my_planning(db, household_id, current_user.id, data.plans_together)


@router.get("/meal-plan", response_model=FamilyPlanWeekResponse)
def family_week_endpoint(
    household_id: int, start: date, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Планы питания всей семьи на 7 дней (без калорий). Запрос: GET /households/1/meal-plan?start=2026-10-26."""
    return get_family_week(db, household_id, current_user.id, start)


@router.post("/meal-plan/generate", response_model=FamilyPlanGenerateResponse)
def family_generate_endpoint(
    household_id: int,
    data: FamilyPlanGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Составляет планы всем участникам и общий ужин.

    Тело: {"start": "2026-10-26", "days": 7, "overwrite": false, "batch_days": 2, "shared_meal_types": ["dinner"]}
    Ответ: {"members": [{"user_id": 1, "name": "Даня", "created_meals": 28, "replaced_meals": 0,
                         "skipped_days": []}], "shared_meals": 7, "warnings": []}
    """
    return generate_family_plan(db, household_id, current_user.id, data)


@router.get("/shopping-list", response_model=ShoppingListResponse)
def family_shopping_list_endpoint(
    household_id: int,
    start: date,
    days: Annotated[int, Query(ge=1, le=14)] = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Общий список закупок: продукты планов всех участников, сложенные вместе.

    Запрос: GET /households/1/shopping-list?start=2026-10-26&days=7
    """
    names = together_members(db, household_id, current_user.id)
    return build_household_shopping_list(db, household_id, names, start, days)


@router.put("/shopping-list/checks", status_code=204)
def family_set_check_endpoint(
    household_id: int,
    data: ShoppingCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Отметка «куплено» в общем списке; видно, кто её поставил. Тело: {"start": "2026-10-26", "key": "food:12", "checked": true}."""
    together_members(db, household_id, current_user.id)
    set_household_check(db, household_id, current_user.id, data)
    return Response(status_code=204)


@router.delete("/shopping-list/checks", status_code=204)
def family_clear_checks_endpoint(
    household_id: int, start: date, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Снимает все отметки общего списка: DELETE /households/1/shopping-list/checks?start=2026-10-26."""
    together_members(db, household_id, current_user.id)
    clear_household_checks(db, household_id, start)
    return Response(status_code=204)


@router.get("/cooking-plan", response_model=CookingPlanResponse)
def family_cooking_plan_endpoint(
    household_id: int,
    start: date,
    days: Annotated[int, Query(ge=1, le=14)] = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Общий план готовки: блюда на нескольких человек готовятся одним подходом."""
    names = together_members(db, household_id, current_user.id)
    return build_household_cooking_plan(db, names, ZoneInfo(current_user.timezone or "UTC"), start, days)
