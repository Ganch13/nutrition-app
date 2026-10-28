"""Эндпоинты расписания (шаг 64): изменение/удаление событий, серии и недельный вид.

Создание одиночного события и список событий за период остаются в main.py
(POST/GET /users/{user_id}/schedule-events).
"""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from access import require_same_user
from database import get_db
from error_handling import register_error_map
from schedule_services import (
    ScheduleEventMissingError,
    ScheduleOverlapError,
    ScheduleTimeRangeError,
    ScheduleUserNotFoundError,
    create_schedule_series,
    delete_schedule_event,
    get_week,
    update_schedule_event,
)
from schemas import (
    ScheduleEventResponse,
    ScheduleEventUpdate,
    ScheduleSeriesCreate,
    ScheduleSeriesResponse,
    ScheduleWeekResponse,
)

router = APIRouter(
    prefix="/users/{user_id}",
    tags=["schedule"],
    # Все пути ниже доступны только владельцу данных
    dependencies=[Depends(require_same_user)],
)

ERROR_RESPONSES = {
    ScheduleUserNotFoundError: (404, "Пользователь не найден"),
    ScheduleEventMissingError: (404, "Событие расписания не найдено"),
    ScheduleTimeRangeError: (422, "Окончание должно быть позже начала"),
}


def register_error_handlers(app: FastAPI) -> None:
    register_error_map(app, ERROR_RESPONSES)

    # Текст ошибки пересечения свой у каждого случая (с названием и временем второго события)
    async def overlap_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=409, content={"detail": exc.message})  # type: ignore[attr-defined]

    app.add_exception_handler(ScheduleOverlapError, overlap_handler)


@router.patch("/schedule-events/{event_id}", response_model=ScheduleEventResponse)
def update_event_endpoint(
    user_id: int,
    event_id: int,
    data: ScheduleEventUpdate,
    db: Session = Depends(get_db),
):
    """Меняет поля события.

    Запрос: PATCH /users/1/schedule-events/5 с телом {"title": "Работа из дома", "location": "Дома"}
    """
    return update_schedule_event(db, user_id, event_id, data)


@router.delete("/schedule-events/{event_id}", status_code=204)
def delete_event_endpoint(
    user_id: int,
    event_id: int,
    scope: Annotated[Literal["one", "following"], Query()] = "one",
    db: Session = Depends(get_db),
):
    """Удаляет событие.

    DELETE /users/1/schedule-events/5               — только это событие
    DELETE /users/1/schedule-events/5?scope=following — это и все следующие в серии
    """
    delete_schedule_event(db, user_id, event_id, scope)
    return Response(status_code=204)


@router.post("/schedule-events/series", response_model=ScheduleSeriesResponse, status_code=201)
def create_series_endpoint(
    user_id: int,
    data: ScheduleSeriesCreate,
    db: Session = Depends(get_db),
):
    """Создаёт повторяющиеся события по дням недели.

    Пример тела:
    {"event_type": "work", "title": "Работа", "weekdays": [0,1,2,3,4],
     "start_time": "09:00", "end_time": "18:00", "from_date": "2026-10-26",
     "weeks": 4, "location": "Офис"}
    """
    series_id, events = create_schedule_series(db, user_id, data)
    return ScheduleSeriesResponse(series_id=series_id, events=events)


@router.get("/schedule/week", response_model=ScheduleWeekResponse)
def week_endpoint(
    user_id: int,
    start: date,
    db: Session = Depends(get_db),
):
    """Расписание на 7 дней с даты start: события, тренировки и пересечения.

    Запрос: GET /users/1/schedule/week?start=2026-10-26
    """
    return get_week(db, user_id, start)
