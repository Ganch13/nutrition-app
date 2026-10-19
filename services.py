from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from models import TrainingSession, ScheduleEvent, ScheduleEvent, Goal, Household, HouseholdMember, User, WeightRecord
from schemas import  TrainingSessionCreate, ScheduleEventCreate, GoalCreate, UserCreate, WeightRecordCreate
from sqlalchemy import select, case
from datetime import datetime, date


def create_user(db: Session, user_data: UserCreate) -> User:
    db_user = User(
        name=user_data.name,
        birth_date=user_data.birth_date,
        sex=user_data.sex,
        height_cm=user_data.height_cm,
        occupation=user_data.occupation,
        timezone=user_data.timezone,
    )

    try:
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

    except SQLAlchemyError:
        db.rollback()
        raise

    return db_user


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)

def create_household(
    db: Session,
    name: str,
    owner_user_id: int,
) -> Household | None:
    owner = db.get(User, owner_user_id)

    if owner is None:
        return None

    household = Household(name=name)

    try:
        db.add(household)

        # Отправляем INSERT в БД, чтобы получить id,
        # но пока не фиксируем транзакцию.
        db.flush()

        member = HouseholdMember(
            household_id=household.id,
            user_id=owner.id,
            role="owner",
        )

        db.add(member)

        # Фиксируем обе записи одной транзакцией.
        db.commit()
        db.refresh(household)

    except SQLAlchemyError:
        db.rollback()
        raise

    return household


class HouseholdNotFoundError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


class HouseholdMemberAlreadyExistsError(Exception):
    pass


class GoalNotFoundError(Exception):
    pass


class InvalidGoalDatesError(Exception):
    pass


class ScheduleEventNotFoundError(Exception):
    pass


class ScheduleEventAlreadyLinkedError(Exception):
    pass


def add_household_member(
    db: Session,
    household_id: int,
    user_id: int,
) -> HouseholdMember:
    household = db.get(Household, household_id)

    if household is None:
        raise HouseholdNotFoundError()

    user = db.get(User, user_id)

    if user is None:
        raise UserNotFoundError()

    existing_member = db.get(
        HouseholdMember,
        (household_id, user_id),
    )

    if existing_member is not None:
        raise HouseholdMemberAlreadyExistsError()

    member = HouseholdMember(
        household_id=household_id,
        user_id=user_id,
        role="member",
    )

    try:
        db.add(member)
        db.commit()
        db.refresh(member)

    except SQLAlchemyError:
        db.rollback()
        raise

    return member

def get_household_members(
    db: Session,
    household_id: int,
) -> list[HouseholdMember]:
    household = db.get(Household, household_id)

    if household is None:
        raise HouseholdNotFoundError()

    statement = (
        select(HouseholdMember)
        .where(HouseholdMember.household_id == household_id)
        .order_by(
            HouseholdMember.joined_at,
            HouseholdMember.user_id,
        )
    )

    return list(db.scalars(statement).all())

def update_user(
    db: Session,
    user_id: int,
    changes: dict[str, object],
) -> User | None:
    db_user = db.get(User, user_id)

    if db_user is None:
        return None

    try:
        for field_name, value in changes.items():
            setattr(db_user, field_name, value)

        db.commit()
        db.refresh(db_user)

    except SQLAlchemyError:
        db.rollback()
        raise

    return db_user

def create_weight_record(
    db: Session,
    user_id: int,
    record_data: WeightRecordCreate,
) -> WeightRecord:
    user = db.get(User, user_id)

    if user is None:
        raise UserNotFoundError()

    record = WeightRecord(
        user_id=user_id,
        measurement_date=record_data.measurement_date,
        weight_kg=record_data.weight_kg,
        body_fat_percent=record_data.body_fat_percent,
        notes=record_data.notes,
    )

    try:
        db.add(record)
        db.commit()
        db.refresh(record)

    except SQLAlchemyError:
        db.rollback()
        raise

    return record


def get_weight_records(
    db: Session,
    user_id: int,
) -> list[WeightRecord]:
    user = db.get(User, user_id)

    if user is None:
        raise UserNotFoundError()

    statement = (
        select(WeightRecord)
        .where(WeightRecord.user_id == user_id)
        .order_by(
            WeightRecord.measurement_date.desc(),
            WeightRecord.created_at.desc(),
            WeightRecord.id.desc(),
        )
    )

    return list(db.scalars(statement).all())



def create_goal(
    db: Session,
    user_id: int,
    goal_data: GoalCreate,
) -> Goal:
    # Проверяем, существует ли пользователь
    user = db.get(User, user_id)

    if user is None:
        raise UserNotFoundError()

    # Создаём объект цели для PostgreSQL
    goal = Goal(
        user_id=user_id,
        **goal_data.model_dump(),
    )

    try:
        # Добавляем цель в сессию SQLAlchemy
        db.add(goal)

        # Сохраняем запись в базе
        db.commit()

        # Получаем актуальные данные, назначенные базой
        db.refresh(goal)

    except SQLAlchemyError:
        # При ошибке откатываем незавершённую транзакцию
        db.rollback()
        raise

    return goal


def get_user_goals(
    db: Session,
    user_id: int,
) -> list[Goal]:
    # Проверяем, существует ли пользователь
    user = db.get(User, user_id)

    if user is None:
        raise UserNotFoundError()

    # Определяем порядок статусов для отображения
    status_order = case(
        (Goal.status == "active", 1),
        (Goal.status == "paused", 2),
        (Goal.status == "completed", 3),
        (Goal.status == "cancelled", 4),
        else_=5,
    )

    # Получаем цели пользователя в удобном порядке
    statement = (
        select(Goal)
        .where(Goal.user_id == user_id)
        .order_by(
            status_order.asc(),  # Сначала активные цели
            Goal.priority.asc(),  # Затем по приоритету: 1 — высший
            Goal.start_date.desc(),  # Затем по дате начала
            Goal.id.desc(),  # Для стабильного порядка при совпадениях
        )
    )

    # Возвращаем список целей
    return list(db.scalars(statement).all())


def update_goal(
    db: Session,
    user_id: int,
    goal_id: int,
    changes: dict[str, object],
) -> Goal:
    # Проверяем существование пользователя
    user = db.get(User, user_id)

    if user is None:
        raise UserNotFoundError()

    # Получаем цель по её идентификатору
    goal = db.get(Goal, goal_id)

    # Не разрешаем изменять чужую цель
    if goal is None or goal.user_id != user_id:
        raise GoalNotFoundError()

    # Проверяем итоговое сочетание дат, включая старые значения
    new_start_date = changes.get("start_date", goal.start_date)
    new_target_date = changes.get("target_date", goal.target_date)

    if (
        new_target_date is not None
        and new_target_date < new_start_date
    ):
        raise InvalidGoalDatesError()

    try:
        # Применяем только переданные изменения
        for field_name, value in changes.items():
            setattr(goal, field_name, value)

        # Сохраняем изменения
        db.commit()

        # Получаем актуальные значения из базы
        db.refresh(goal)

    except SQLAlchemyError:
        # Откатываем незавершённую транзакцию
        db.rollback()
        raise

    return goal


def create_schedule_event(
    db: Session,
    user_id: int,
    event_data: ScheduleEventCreate,
) -> ScheduleEvent:
    # Проверяем, существует ли пользователь
    user = db.get(User, user_id)

    if user is None:
        raise UserNotFoundError()

    # Создаём событие, привязанное к пользователю
    event = ScheduleEvent(
        user_id=user_id,
        **event_data.model_dump(),
    )

    try:
        # Добавляем событие в сессию
        db.add(event)

        # Сохраняем запись в PostgreSQL
        db.commit()

        # Получаем назначенные базой значения
        db.refresh(event)

    except SQLAlchemyError:
        # Откатываем незавершённую транзакцию
        db.rollback()
        raise

    return event


def get_schedule_events(
    db: Session,
    user_id: int,
    from_at: datetime,
    to_at: datetime,
) -> list[ScheduleEvent]:
    # Проверяем, существует ли пользователь
    user = db.get(User, user_id)

    if user is None:
        raise UserNotFoundError()

    # Выбираем события, пересекающиеся с заданным периодом
    statement = (
        select(ScheduleEvent)
        .where(
            ScheduleEvent.user_id == user_id,
            ScheduleEvent.start_at < to_at,
            ScheduleEvent.end_at > from_at,
        )
        .order_by(
            ScheduleEvent.start_at.asc(),
            ScheduleEvent.id.asc(),
        )
    )

    # Возвращаем события в хронологическом порядке
    return list(db.scalars(statement).all())


def create_training_session(
    db: Session,
    user_id: int,
    session_data: TrainingSessionCreate,
) -> TrainingSession:
    # Проверяем существование пользователя
    user = db.get(User, user_id)

    if user is None:
        raise UserNotFoundError()

    # Проверяем связанную запись расписания, если она указана
    schedule_event_id = session_data.schedule_event_id

    if schedule_event_id is not None:
        schedule_event = db.get(ScheduleEvent, schedule_event_id)

        # Событие должно существовать и принадлежать этому пользователю
        if (
            schedule_event is None
            or schedule_event.user_id != user_id
        ):
            raise ScheduleEventNotFoundError()

        # Одно событие расписания нельзя связать с двумя сессиями
        existing_session = db.scalar(
            select(TrainingSession).where(
                TrainingSession.schedule_event_id == schedule_event_id
            )
        )

        if existing_session is not None:
            raise ScheduleEventAlreadyLinkedError()

    # Создаём объект тренировочной сессии
    training_session = TrainingSession(
        user_id=user_id,
        **session_data.model_dump(),
    )

    try:
        # Добавляем объект в сессию SQLAlchemy
        db.add(training_session)

        # Сохраняем запись в PostgreSQL
        db.commit()

        # Получаем id и другие значения, назначенные базой
        db.refresh(training_session)

    except SQLAlchemyError:
        # Откатываем транзакцию при ошибке базы
        db.rollback()
        raise

    return training_session


def get_training_sessions(
    db: Session,
    user_id: int,
) -> list[TrainingSession]:
    # Проверяем существование пользователя
    user = db.get(User, user_id)

    if user is None:
        raise UserNotFoundError()

    # Получаем его тренировочные сессии от новых к старым
    statement = (
        select(TrainingSession)
        .where(TrainingSession.user_id == user_id)
        .order_by(
            TrainingSession.start_at.desc(),
            TrainingSession.id.desc(),
        )
    )

    return list(db.scalars(statement).all())