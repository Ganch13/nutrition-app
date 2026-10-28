"""Бизнес-логика расписания (шаг 64): изменение и удаление событий,
повторяющиеся серии и недельный вид с поиском пересечений.

Правило пересечений: два события не могут идти одновременно. Исключение — событие-контейнер
(is_container, например «Работа 9–18»): внутри него могут быть другие события, если они целиком
помещаются в его время (обед 14–15). Вложенные события между собой не пересекаются, но могут идти
подряд (14:00–15:00 и 15:00–15:30). Приложение само ничего не вкладывает: контейнер отмечает человек.
"""

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models import ScheduleEvent, TrainingSession, User
from schemas import (
    ScheduleConflict,
    ScheduleEventUpdate,
    ScheduleItem,
    ScheduleItemRef,
    ScheduleSeriesCreate,
    ScheduleWeekResponse,
)

# Статусы тренировок, которые больше не занимают время в расписании
INACTIVE_TRAINING_STATUSES = {"skipped", "cancelled"}


class ScheduleUserNotFoundError(Exception):
    # Пользователь не найден
    pass


class ScheduleEventMissingError(Exception):
    # Событие не найдено у этого пользователя
    pass


class ScheduleTimeRangeError(Exception):
    # После изменения окончание оказалось не позже начала
    pass


class ScheduleOverlapError(Exception):
    """Событие пересекается с другим, а вложить его нельзя. message — готовый текст для человека."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _contains(outer_start: datetime, outer_end: datetime, inner_start: datetime, inner_end: datetime) -> bool:
    """True, если промежуток inner целиком внутри outer (границы могут совпадать)."""
    return outer_start <= inner_start and inner_end <= outer_end


def _may_overlap(
    first: tuple[datetime, datetime, bool],
    second: tuple[datetime, datetime, bool],
) -> bool:
    """Можно ли двум пересекающимся промежуткам (начало, конец, контейнер ли) идти одновременно.

    Можно только так: один — контейнер, второй — не контейнер и целиком внутри первого.
    Пример: «Работа 9–18» (контейнер) и «Обед 14–15» → True; «Работа 9–18» без отметки и обед → False.
    """
    for outer, inner in ((first, second), (second, first)):
        if outer[2] and not inner[2] and _contains(outer[0], outer[1], inner[0], inner[1]):
            return True
    return False


def _period_text(start: datetime, end: datetime, tz: ZoneInfo) -> str:
    """Время события в поясе пользователя: "27.10 09:00–18:00" или "27.10 23:00–28.10 07:00"."""
    local_start, local_end = start.astimezone(tz), end.astimezone(tz)
    end_format = "%H:%M" if local_end.date() == local_start.date() else "%d.%m %H:%M"
    return f"{local_start:%d.%m %H:%M}–{local_end.strftime(end_format)}"


def _overlap_message(title: str, is_container: bool, other: ScheduleEvent, tz: ZoneInfo) -> str:
    """Понятное объяснение, почему событие title нельзя сохранить рядом с other."""
    when = _period_text(other.start_at, other.end_at, tz)
    if is_container and other.is_container:
        return f"Блок «{title}» пересекается с блоком «{other.title}» ({when}). Два блока не могут идти одновременно."
    if other.is_container:
        return (
            f"«{title}» выходит за границы блока «{other.title}» ({when}). "
            "Вложенное событие должно целиком помещаться во время блока."
        )
    if is_container:
        return (
            f"Событие «{other.title}» ({when}) только частично попадает в блок «{title}». "
            "Измените время, чтобы оно было целиком внутри блока или вне его."
        )
    return (
        f"«{title}» пересекается с событием «{other.title}» ({when}). Два события не могут идти одновременно. "
        "Если одно из них — блок, внутри которого бывают другие события (например, работа), "
        "отметьте у него «Внутри этого блока могут быть другие события»."
    )


def check_overlaps(
    db: Session,
    user_id: int,
    candidates: list[tuple[str, datetime, datetime, bool]],
    exclude_id: int | None = None,
) -> None:
    """Проверяет новые или изменённые события перед сохранением; при нарушении бросает ScheduleOverlapError.

    candidates — события, которые собираемся сохранить: (название, начало, конец, контейнер ли).
    exclude_id — id изменяемого события: со своей старой версией оно не сравнивается.
    Сравниваются и с сохранёнными событиями пользователя, и друг с другом (для серий).
    Тренировки (раздел «Тренировки») здесь не проверяются: их пересечения показывает недельный вид.
    Пример: в базе «Работа 9–18» без отметки контейнера, сохраняем «Обед 14–15» →
    ошибка «…пересекается с событием «Работа»…».
    """
    if not candidates:
        return
    tz = _user_timezone(db, user_id)
    first_start = min(item[1] for item in candidates)
    last_end = max(item[2] for item in candidates)

    query = select(ScheduleEvent).where(
        ScheduleEvent.user_id == user_id,
        ScheduleEvent.start_at < last_end,
        ScheduleEvent.end_at > first_start,
    )
    if exclude_id is not None:
        query = query.where(ScheduleEvent.id != exclude_id)
    existing = db.scalars(query.order_by(ScheduleEvent.start_at, ScheduleEvent.id)).all()

    for index, (title, start, end, is_container) in enumerate(candidates):
        for other in existing:
            if not (start < other.end_at and other.start_at < end):
                continue
            if not _may_overlap((start, end, is_container), (other.start_at, other.end_at, other.is_container)):
                raise ScheduleOverlapError(_overlap_message(title, is_container, other, tz))
        for _, other_start, other_end, other_container in candidates[index + 1:]:
            if not (start < other_end and other_start < end):
                continue
            if not _may_overlap((start, end, is_container), (other_start, other_end, other_container)):
                raise ScheduleOverlapError(
                    f"События серии «{title}» пересекаются друг с другом "
                    f"({_period_text(start, end, tz)} и {_period_text(other_start, other_end, tz)})."
                )


def _user_timezone(db: Session, user_id: int) -> ZoneInfo:
    """Возвращает часовой пояс пользователя, например ZoneInfo("Europe/Moscow")."""
    user = db.get(User, user_id)
    if user is None:
        raise ScheduleUserNotFoundError
    return ZoneInfo(user.timezone or "UTC")


def _get_event(db: Session, user_id: int, event_id: int) -> ScheduleEvent:
    """Находит событие, принадлежащее пользователю; чужое считается ненайденным."""
    event = db.scalar(
        select(ScheduleEvent).where(
            ScheduleEvent.id == event_id,
            ScheduleEvent.user_id == user_id,
        )
    )
    if event is None:
        raise ScheduleEventMissingError
    return event


def update_schedule_event(
    db: Session,
    user_id: int,
    event_id: int,
    data: ScheduleEventUpdate,
) -> ScheduleEvent:
    """Меняет только переданные поля события.

    Пример: data = {"title": "Работа из дома"} → меняется название, время остаётся.
    Если пришло только start_at или только end_at, порядок сверяется с сохранённой
    второй датой (иначе можно было бы получить окончание раньше начала).
    """
    event = _get_event(db, user_id, event_id)

    changes = data.model_dump(exclude_unset=True)
    new_start = changes.get("start_at", event.start_at)
    new_end = changes.get("end_at", event.end_at)
    if new_end <= new_start:
        raise ScheduleTimeRangeError

    check_overlaps(
        db,
        user_id,
        [(changes.get("title", event.title), new_start, new_end, changes.get("is_container", event.is_container))],
        exclude_id=event.id,
    )

    try:
        for field, value in changes.items():
            setattr(event, field, value)
        db.commit()
        db.refresh(event)
    except SQLAlchemyError:
        db.rollback()
        raise
    return event


def delete_schedule_event(
    db: Session,
    user_id: int,
    event_id: int,
    scope: str = "one",
) -> int:
    """Удаляет событие; возвращает, сколько событий удалено.

    scope="one" — только это событие.
    scope="following" — это и все последующие события той же серии
    (как «это и следующие» в календарях). У одиночного события равно "one".
    Привязанные тренировки не удаляются: у них просто очищается связь с событием.
    """
    event = _get_event(db, user_id, event_id)

    if scope == "following" and event.series_id is not None:
        ids = list(
            db.scalars(
                select(ScheduleEvent.id).where(
                    ScheduleEvent.user_id == user_id,
                    ScheduleEvent.series_id == event.series_id,
                    ScheduleEvent.start_at >= event.start_at,
                )
            ).all()
        )
    else:
        ids = [event.id]

    try:
        # Освобождаем тренировки, привязанные к удаляемым событиям
        db.execute(
            update(TrainingSession)
            .where(TrainingSession.schedule_event_id.in_(ids))
            .values(schedule_event_id=None)
        )
        db.execute(delete(ScheduleEvent).where(ScheduleEvent.id.in_(ids)))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return len(ids)


def create_schedule_series(
    db: Session,
    user_id: int,
    data: ScheduleSeriesCreate,
) -> tuple[str, list[ScheduleEvent]]:
    """Создаёт отдельные события на каждый подходящий день недели.

    Пример: weekdays=[0,1,2,3,4], from_date=2026-10-26 (пн), weeks=2 → 10 событий
    «Работа 09:00–18:00» с 26 октября по 6 ноября, у всех один series_id.
    Время считается в часовом поясе пользователя. Каждое событие — обычная запись
    ScheduleEvent, поэтому другие части приложения видят их без особых правил.
    """
    tz = _user_timezone(db, user_id)
    series_id = str(uuid.uuid4())
    overnight = data.end_time <= data.start_time

    events: list[ScheduleEvent] = []
    for offset in range(data.weeks * 7):
        day = data.from_date + timedelta(days=offset)
        if day.weekday() not in data.weekdays:
            continue
        end_day = day + timedelta(days=1) if overnight else day
        events.append(
            ScheduleEvent(
                user_id=user_id,
                event_type=data.event_type,
                title=data.title,
                start_at=datetime.combine(day, data.start_time, tzinfo=tz),
                end_at=datetime.combine(end_day, data.end_time, tzinfo=tz),
                location=data.location,
                notes=data.notes,
                series_id=series_id,
                is_container=data.is_container,
            )
        )

    check_overlaps(
        db,
        user_id,
        [(event.title, event.start_at, event.end_at, event.is_container) for event in events],
    )

    try:
        db.add_all(events)
        db.commit()
        for event in events:
            db.refresh(event)
    except SQLAlchemyError:
        db.rollback()
        raise
    return series_id, events


def _overlaps(a: ScheduleItem, b: ScheduleItem) -> bool:
    """True, если интервалы пересекаются. Вплотную (конец = начало) — не пересечение."""
    return a.start_at < b.end_at and b.start_at < a.end_at


def _containers_of(items: list[ScheduleItem]) -> dict[tuple[str, int], int]:
    """Для каждого элемента, вложенного в событие-контейнер, — id этого контейнера.

    Пример: «Работа 9–18» (контейнер, id 3) и «Обед 14–15» (id 7) → {("event", 7): 3}.
    Если подходящих контейнеров несколько (старые данные), берётся самый короткий.
    """
    containers = [item for item in items if item.kind == "event" and item.is_container]
    result: dict[tuple[str, int], int] = {}
    for item in items:
        if item.is_container:
            continue
        fitting = [
            container
            for container in containers
            if _contains(container.start_at, container.end_at, item.start_at, item.end_at)
        ]
        if fitting:
            best = min(fitting, key=lambda container: container.end_at - container.start_at)
            result[(item.kind, item.id)] = best.id
    return result


def find_conflicts(
    items: list[ScheduleItem],
    linked_pairs: set[tuple[int, int]],
) -> list[ScheduleConflict]:
    """Находит пары элементов, которые идут одновременно, хотя не должны.

    items — события и тренировки недели.
    linked_pairs — пары (id тренировки, id события расписания), которые описывают
    одно и то же занятие; такие пары конфликтом не считаются.

    Пересекаться можно только контейнеру и элементу, целиком попавшему внутрь него.
    Пример: «Работа 09:00–18:00» без отметки контейнера и «Тренировка 17:30–19:00» → один конфликт.
    Отменённые и пропущенные тренировки времени не занимают.
    """
    candidates = [item for item in items if item.status not in INACTIVE_TRAINING_STATUSES]

    conflicts: list[ScheduleConflict] = []
    for index, first in enumerate(candidates):
        for second in candidates[index + 1:]:
            if not _overlaps(first, second):
                continue
            if _may_overlap(
                (first.start_at, first.end_at, first.is_container),
                (second.start_at, second.end_at, second.is_container),
            ):
                continue
            # Событие типа «workout» и привязанная к нему тренировка — одно и то же
            training, event = (first, second) if first.kind == "training" else (second, first)
            if (
                training.kind == "training"
                and event.kind == "event"
                and (training.id, event.id) in linked_pairs
            ):
                continue
            conflicts.append(
                ScheduleConflict(
                    first=ScheduleItemRef(kind=first.kind, id=first.id, title=first.title),
                    second=ScheduleItemRef(kind=second.kind, id=second.id, title=second.title),
                )
            )
    return conflicts


def get_week(db: Session, user_id: int, start: date) -> ScheduleWeekResponse:
    """Собирает расписание на 7 дней, начиная с даты start (обычно понедельник).

    Границы недели считаются по часовому поясу пользователя. В ответ попадают
    события и тренировки, пересекающиеся с неделей, отсортированные по началу,
    и список найденных пересечений.
    """
    tz = _user_timezone(db, user_id)
    from_at = datetime.combine(start, time.min, tzinfo=tz)
    to_at = datetime.combine(start + timedelta(days=7), time.min, tzinfo=tz)

    events = db.scalars(
        select(ScheduleEvent).where(
            ScheduleEvent.user_id == user_id,
            ScheduleEvent.start_at < to_at,
            ScheduleEvent.end_at > from_at,
        )
    ).all()
    sessions = db.scalars(
        select(TrainingSession).where(
            TrainingSession.user_id == user_id,
            TrainingSession.start_at < to_at,
            TrainingSession.end_at > from_at,
        )
    ).all()

    items = [
        ScheduleItem(
            kind="event",
            id=event.id,
            title=event.title,
            category=event.event_type,
            start_at=event.start_at,
            end_at=event.end_at,
            location=event.location,
            series_id=event.series_id,
            is_container=event.is_container,
        )
        for event in events
    ] + [
        ScheduleItem(
            kind="training",
            id=session.id,
            title=session.name,
            category="workout",
            start_at=session.start_at,
            end_at=session.end_at,
            status=session.status,
        )
        for session in sessions
    ]
    items.sort(key=lambda item: (item.start_at, item.kind, item.id))
    parents = _containers_of(items)
    for item in items:
        item.parent_id = parents.get((item.kind, item.id))

    linked_pairs = {
        (session.id, session.schedule_event_id)
        for session in sessions
        if session.schedule_event_id is not None
    }

    return ScheduleWeekResponse(
        start=start,
        end=start + timedelta(days=6),
        timezone=str(tz),
        items=items,
        conflicts=find_conflicts(items, linked_pairs),
    )
