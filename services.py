from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from models import MealEntry, Workout, TrainingSession, ScheduleEvent, ScheduleEvent, Goal, Household, HouseholdMember, User, WeightRecord
from schemas import  LoginRequest, RegisterRequest, MealEntryCreate, WorkoutUpdate, WorkoutCreate, TrainingSessionCreate, ScheduleEventCreate, GoalCreate, UserCreate, WeightRecordCreate
from sqlalchemy import select, case, func
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from security import hash_password, verify_password




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


class WorkoutSessionNotFoundError(Exception):
    # Указанная сессия не найдена у этого пользователя
    pass


class WorkoutTimeOutsideSessionError(Exception):
    # Время блока выходит за пределы сессии
    pass


class WorkoutSaveError(Exception):
    # Не получилось сохранить блок в базе данных
    pass


class WorkoutNotFoundError(Exception):
    # Блок не найден в указанной сессии
    pass


class MealEntryUserNotFoundError(Exception):
    # Пользователь, для которого создаётся запись, не найден
    pass


class MealEntrySaveError(Exception):
    # Ошибка при сохранении записи о приёме пищи
    pass


class EmailAlreadyRegisteredError(Exception):
    """Ошибка: пользователь с таким email уже зарегистрирован."""
    pass


class InvalidCredentialsError(Exception):
    """Ошибка: неверные учётные данные."""
    pass





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



def register_user(db, registration_data: RegisterRequest):
    """Создаёт пользователя и сохраняет только хеш его пароля."""

    # Приводим email к единому регистру.
    email = str(registration_data.email).strip().lower()

    # Проверяем, не зарегистрирован ли такой email.
    existing_user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if existing_user is not None:
        raise EmailAlreadyRegisteredError

    # Отделяем пароль от остальных регистрационных данных.
    user_data = registration_data.model_dump()
    password = user_data.pop("password")
    user_data.pop("email")

    # Создаём пользователя, сохраняя вместо пароля его хеш.
    new_user = User(
        **user_data,
        email=email,
        password_hash=hash_password(password),
    )



    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except IntegrityError:
        # Откатываем транзакцию, если база отклонила запись.
        db.rollback()
        raise EmailAlreadyRegisteredError from None

    return new_user




def authenticate_user(db, login_data: LoginRequest):
    """Находит пользователя и проверяет введённый пароль."""

    # Email приводим к тому же регистру, что и при регистрации.
    email = str(login_data.email).strip().lower()

    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    # Одинаковая ошибка для неизвестного email и неверного пароля.
    if user is None or user.password_hash is None:
        raise InvalidCredentialsError

    if not verify_password(login_data.password, user.password_hash):
        raise InvalidCredentialsError

    return user







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


def get_user_households(
    db: Session,
    user_id: int,
) -> list[dict]:
    """Возвращает домохозяйства пользователя вместе с его ролью в каждом.

    Аргументы:
        db      — сессия базы данных, её выдаёт get_db
        user_id — id пользователя, например 1

    Результат, например:
        [
            {"id": 1, "name": "Дом", "created_at": datetime(...), "role": "owner"},
            {"id": 2, "name": "Дача", "created_at": datetime(...), "role": "member"},
        ]

    Проверять существование пользователя не нужно: сюда попадает только
    тот, кого уже нашла проверка токена.
    """

    # Запрос на языке SQLAlchemy; в SQL это примерно:
    #   SELECT households.*, household_members.role
    #   FROM households
    #   JOIN household_members ON household_members.household_id = households.id
    #   WHERE household_members.user_id = 1
    #   ORDER BY households.created_at, households.id
    #
    # JOIN связывает две таблицы: для каждого домохозяйства находит строки
    # участников. WHERE оставляет только строки нашего пользователя, поэтому
    # чужие домохозяйства в результат не попадают.
    statement = (
        select(Household, HouseholdMember.role)
        # select_from явно говорит, что JOIN идёт от таблицы households
        .select_from(Household)
        .join(HouseholdMember, HouseholdMember.household_id == Household.id)
        .where(HouseholdMember.user_id == user_id)
        # Сначала старые домохозяйства; id нужен для стабильного порядка,
        # если у двух домохозяйств одно и то же время создания
        .order_by(Household.created_at.asc(), Household.id.asc())
    )

    # rows — список строк; в каждой строке два значения:
    # (объект Household, роль), например (Household(id=1, name="Дом"), "owner")
    rows = db.execute(statement).all()

    # Превращаем каждую строку в словарь, который понимает UserHouseholdResponse.
    # В цикле household — объект домохозяйства, role — строка с ролью.
    return [
        {
            "id": household.id,
            "name": household.name,
            "created_at": household.created_at,
            "role": role,
        }
        for household, role in rows
    ]

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


def create_workout(
    db: Session,
    user_id: int,
    training_session_id: int,
    workout_data: WorkoutCreate,
) -> Workout:
    # Находим сессию, принадлежащую указанному пользователю
    training_session = db.scalar(
        select(TrainingSession).where(
            TrainingSession.id == training_session_id,
            TrainingSession.user_id == user_id,
        )
    )

    # Не позволяем работать с чужой или несуществующей сессией
    if training_session is None:
        raise WorkoutSessionNotFoundError

    # Проверяем, что блок полностью помещается во временные рамки сессии
    if (
        workout_data.start_at < training_session.start_at
        or workout_data.end_at > training_session.end_at
    ):
        raise WorkoutTimeOutsideSessionError

    # Создаём объект блока тренировки
    workout = Workout(
        training_session_id=training_session_id,
        **workout_data.model_dump(),
    )

    try:
        # Добавляем блок в сессию базы данных
        db.add(workout)

        # Сохраняем изменения в PostgreSQL
        db.commit()

        # Получаем из базы созданный id и другие значения по умолчанию
        db.refresh(workout)

        return workout

    except SQLAlchemyError as exc:
        # Отменяем незавершённую транзакцию при ошибке БД
        db.rollback()

        # Передаём ошибку на уровень API
        raise WorkoutSaveError from exc


def get_workouts_for_training_session(
    db: Session,
    user_id: int,
    training_session_id: int,
) -> list[Workout]:
    # Проверяем, что сессия принадлежит указанному пользователю
    training_session = db.scalar(
        select(TrainingSession).where(
            TrainingSession.id == training_session_id,
            TrainingSession.user_id == user_id,
        )
    )

    if training_session is None:
        raise WorkoutSessionNotFoundError

    # Возвращаем блоки этой сессии по времени начала
    workouts = db.scalars(
        select(Workout)
        .where(Workout.training_session_id == training_session_id)
        .order_by(Workout.start_at, Workout.id)
    ).all()

    return list(workouts)


def update_workout(
    db: Session,
    user_id: int,
    training_session_id: int,
    workout_id: int,
    workout_data: WorkoutUpdate,
) -> Workout:
    # Проверяем принадлежность сессии пользователю
    training_session = db.scalar(
        select(TrainingSession).where(
            TrainingSession.id == training_session_id,
            TrainingSession.user_id == user_id,
        )
    )

    if training_session is None:
        raise WorkoutSessionNotFoundError

    # Находим блок внутри указанной сессии
    workout = db.scalar(
        select(Workout).where(
            Workout.id == workout_id,
            Workout.training_session_id == training_session_id,
        )
    )

    if workout is None:
        raise WorkoutNotFoundError

    # Получаем только те поля, которые клиент действительно передал
    update_data = workout_data.model_dump(exclude_unset=True)

    try:
        # Обновляем переданные значения
        for field, value in update_data.items():
            setattr(workout, field, value)

        # Сохраняем изменения в PostgreSQL
        db.commit()

        # Обновляем объект значениями из базы
        db.refresh(workout)

        return workout

    except SQLAlchemyError as exc:
        # Отменяем транзакцию при ошибке базы данных
        db.rollback()

        # Передаём ошибку на уровень API
        raise WorkoutSaveError from exc


def create_meal_entry(
    db: Session,
    user_id: int,
    meal_data: MealEntryCreate,
) -> MealEntry:
    # Проверяем, что пользователь существует
    user = db.get(User, user_id)

    if user is None:
        raise MealEntryUserNotFoundError

    # Создаём объект записи о приёме пищи
    meal_entry = MealEntry(
        user_id=user_id,
        **meal_data.model_dump(),
    )

    try:
        # Добавляем запись в сессию базы данных
        db.add(meal_entry)

        # Сохраняем изменения в PostgreSQL
        db.commit()

        # Получаем ID и значения, сформированные базой данных
        db.refresh(meal_entry)

        return meal_entry

    except SQLAlchemyError as exc:
        # Отменяем транзакцию при ошибке базы данных
        db.rollback()

        # Передаём ошибку уровню API
        raise MealEntrySaveError from exc


def get_meal_entries(
    db: Session,
    user_id: int,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
) -> list[MealEntry]:
    # Проверяем существование пользователя
    user = db.get(User, user_id)

    if user is None:
        raise MealEntryUserNotFoundError

    # Начинаем формировать запрос для конкретного пользователя
    query = select(MealEntry).where(MealEntry.user_id == user_id)

    # Если задано начало периода, исключаем более ранние записи
    if from_at is not None:
        query = query.where(MealEntry.eaten_at >= from_at)

    # Если задан конец периода, исключаем более поздние записи
    if to_at is not None:
        query = query.where(MealEntry.eaten_at < to_at)

    # Сортируем записи по времени приёма пищи
    query = query.order_by(MealEntry.eaten_at, MealEntry.id)

    # Выполняем запрос и возвращаем список
    return list(db.scalars(query).all())


def get_daily_nutrition_summary(
    db: Session,
    user_id: int,
    target_date: date,
) -> dict:
    # Проверяем существование пользователя
    user = db.get(User, user_id)

    if user is None:
        raise MealEntryUserNotFoundError

    # Определяем начало и конец дня в часовом поясе пользователя
    user_timezone = ZoneInfo(user.timezone or "UTC")

    start_at = datetime.combine(
        target_date,
        time.min,
        tzinfo=user_timezone,
    )
    end_at = datetime.combine(
        target_date + timedelta(days=1),
        time.min,
        tzinfo=user_timezone,
    )

    # Суммируем калории и БЖУ по записям за выбранный день
    result = db.execute(
        select(
            func.count(MealEntry.id),
            func.coalesce(func.sum(MealEntry.calories), 0),
            func.coalesce(func.sum(MealEntry.protein_g), 0),
            func.coalesce(func.sum(MealEntry.fat_g), 0),
            func.coalesce(func.sum(MealEntry.carbs_g), 0),
        ).where(
            MealEntry.user_id == user_id,
            MealEntry.eaten_at >= start_at,
            MealEntry.eaten_at < end_at,
        )
    ).one()

    # Возвращаем агрегированные значения
    return {
        "date": target_date,
        "user_id": user_id,
        "entries_count": result[0],
        "calories": result[1],
        "protein_g": result[2],
        "fat_g": result[3],
        "carbs_g": result[4],
    }