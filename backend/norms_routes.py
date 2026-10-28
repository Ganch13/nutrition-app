"""Эндпоинты норм питания и прогресса целей (шаг 66)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy.orm import Session

from access import require_same_user
from database import get_db
from error_handling import register_error_map
from models import User
from norms_services import (
    NormsUserNotFoundError,
    compute_day_target,
    compute_goal_progress,
    get_settings_response,
    save_settings,
)
from schemas import (
    GoalProgressResponse,
    NutritionSettingsResponse,
    NutritionSettingsUpdate,
    NutritionTargetResponse,
)
from security import get_current_user

router = APIRouter(
    prefix="/users/{user_id}",
    tags=["norms"],
    dependencies=[Depends(require_same_user)],
)

ERROR_RESPONSES = {
    NormsUserNotFoundError: (404, "Пользователь не найден"),
}


def register_error_handlers(app: FastAPI) -> None:
    register_error_map(app, ERROR_RESPONSES)


def _today(user: User) -> date:
    """Сегодняшняя дата в часовом поясе пользователя."""
    return datetime.now(ZoneInfo(user.timezone or "UTC")).date()


@router.get("/nutrition/settings", response_model=NutritionSettingsResponse)
def get_settings_endpoint(user_id: int, db: Session = Depends(get_db)):
    """Настройки расчёта норм. Если их ещё не сохраняли, приходят значения по умолчанию."""
    return get_settings_response(db, user_id)


@router.put("/nutrition/settings", response_model=NutritionSettingsResponse)
def put_settings_endpoint(user_id: int, data: NutritionSettingsUpdate, db: Session = Depends(get_db)):
    """Сохраняет настройки целиком.

    Пример тела: {"activity_level": "light", "meals_per_day": 4,
                  "protein_g_per_kg": 2.0, "calorie_override": null}
    """
    return save_settings(db, user_id, data)


@router.get("/nutrition/targets", response_model=NutritionTargetResponse)
def targets_endpoint(
    user_id: int,
    target_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Норма питания на день: калории, белки, жиры, углеводы и объяснение расчёта.

    GET /users/1/nutrition/targets?target_date=2026-10-27 (без даты — сегодня).
    Если не хватает данных (вес, дата рождения), ответ содержит ready=false и список missing.
    """
    return compute_day_target(db, user_id, target_date or _today(current_user))


@router.get("/goals/progress", response_model=list[GoalProgressResponse])
def goal_progress_endpoint(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Прогресс активных целей: начальный и текущий вес, темп, прогноз даты достижения."""
    return compute_goal_progress(db, user_id, _today(current_user))
