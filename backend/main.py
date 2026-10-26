from fastapi import FastAPI, HTTPException, Depends
from schemas import TrainingSessionUpdate, TokenResponse, LoginRequest, RegisterRequest, DailyNutritionSummary, MealEntryCreate, MealEntryResponse, WorkoutUpdate, WorkoutCreate, WorkoutResponse, TrainingSessionCreate, TrainingSessionResponse, ScheduleEventCreate, ScheduleEventResponse, GoalUpdate, GoalCreate, GoalResponse, WeightRecordCreate, WeightRecordResponse, UserUpdate, HouseholdMemberCreate, HouseholdMemberResponse,HouseholdCreate, HouseholdResponse, UserResponse, UserHouseholdResponse
from database import get_db
from sqlalchemy.orm import Session
from services import (delete_goal, delete_training_session, delete_workout, get_meal_entries_for_day, delete_meal_entry, MealEntryNotFoundError,
                      delete_weight_record, WeightRecordNotFoundError,
                      update_training_session as update_training_session_service,
                      TrainingSessionNotFoundError, get_user_households as get_user_households_service, authenticate_user as authenticate_user_service,
InvalidCredentialsError, register_user as register_user_service,
EmailAlreadyRegisteredError, get_daily_nutrition_summary, MealEntryUserNotFoundError, MealEntrySaveError, create_meal_entry, get_meal_entries, update_workout, WorkoutNotFoundError, WorkoutSessionNotFoundError, WorkoutTimeOutsideSessionError, WorkoutSaveError, create_workout, get_workouts_for_training_session, ScheduleEventAlreadyLinkedError, ScheduleEventNotFoundError, create_training_session as create_training_session_service, get_training_sessions as get_training_sessions_service,create_schedule_event as create_schedule_event_service, get_schedule_events as get_schedule_events_service, GoalNotFoundError, InvalidGoalDatesError,
                       update_goal as update_goal_service, create_goal as create_goal_service, get_user_goals as get_user_goals_service, create_weight_record as create_weight_record_service,
                      get_weight_records as get_weight_records_service, update_user as update_user_service, get_household_members as get_household_members_service,
                      get_user as get_user_service, create_household as create_household_service, HouseholdMemberAlreadyExistsError,
                      HouseholdNotFoundError, UserNotFoundError, add_household_member as add_household_member_service)
from datetime import datetime, date
from security import create_access_token, get_current_user
from models import User, HouseholdMember, Household
from fastapi.middleware.cors import CORSMiddleware
from config import get_cors_origins
from finance_routes import router as finance_router, register_error_handlers
from access import require_household_member
from household_routes import router as household_router
from schemas import HouseholdMemberDetailResponse



app = FastAPI()
# Разрешаем браузеру обращаться к API со страниц frontend.
# Адреса берём из .env, чтобы в production их можно было заменить
# без правки кода.
app.add_middleware(
    CORSMiddleware,
    # Например ["http://localhost:3000"]
    allow_origins=get_cors_origins(),
    # Только методы, которые использует наш API
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],    # Токен идёт в Authorization, тело запросов в формате JSON.
    # Параметр allow_credentials не указываем: он нужен для cookie,
    # а мы их не используем.
    allow_headers=["Authorization", "Content-Type"],
)
# Финансы: эндпоинты /finance/... и преобразование их ошибок в HTTP-ответы
app.include_router(finance_router)
app.include_router(household_router)
register_error_handlers(app)



def require_same_user(
    user_id: int,
    current_user=Depends(get_current_user),
):
    """Разрешает доступ только к собственному профилю."""

    if current_user.id != user_id:
        raise HTTPException(
            status_code=403,
            detail="У вас нет доступа к данным этого пользователя",
        )







@app.get("/hello")
def hello():
    print("Hello World")
    return {"message": "Hello Daniil"}


@app.get("/users/me", response_model=UserResponse)
def get_me_endpoint(current_user: User = Depends(get_current_user)):
    """Возвращает профиль пользователя, которому принадлежит токен.

    Зачем нужен: после входа интерфейс знает только токен. Этим запросом он
    узнаёт id, имя и остальные данные профиля, не зная id заранее.

    Запрос: GET /users/me с заголовком "Authorization: Bearer eyJhbGciOi..."
    Ответ:  {"id": 1, "name": "Me User", "age": None, "birth_date": None,
             "sex": None, "height_cm": 180, "occupation": None,
             "timezone": "UTC", "created_at": "2026-10-22T10:15:00Z"}
    """
    # current_user — объект User из базы. Его уже нашла зависимость
    # get_current_user по токену: User(id=1, name="Me User", ...).
    # Отдельную функцию в services.py не создаём: дополнительных запросов
    # к базе нет, поэтому нет и логики, которую стоило бы выносить.
    #
    # response_model=UserResponse оставит в ответе только разрешённые поля
    # (без email и password_hash) и сам посчитает age по birth_date.
    return current_user

@app.get("/users/{user_id}", response_model=UserResponse,
    dependencies=[Depends(require_same_user)],)
def get_user(
    user_id: int,
    db: Session = Depends(get_db)
):
    db_user = get_user_service(db, user_id)

    if db_user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return db_user


@app.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=201,
)
def register_user_endpoint(
    registration_data: RegisterRequest,
    db: Session = Depends(get_db),
):
    """Регистрирует пользователя."""

    try:
        return register_user_service(
            db=db,
            registration_data=registration_data,
        )
    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=409,
            detail="Этот Email уже зарегистрирован",
        )



@app.post("/auth/login", response_model=TokenResponse)
def login_user(
    login_data: LoginRequest,
    db: Session = Depends(get_db),
):
    """Проверяет учётные данные и выдаёт JWT."""

    try:
        user = authenticate_user_service(
            db=db,
            login_data=login_data,
        )
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=401,
            detail="Неправильный email или password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # В токене сохраняем идентификатор пользователя.
    access_token = create_access_token(
        data={"sub": str(user.id)}
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
    )




@app.post(
    "/households",
    response_model=HouseholdResponse,
    status_code=201,
)
def create_household_endpoint(
    household: HouseholdCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Создаёт домохозяйство для вошедшего пользователя."""
    db_household = create_household_service(
        db=db,
        name=household.name,
        owner_user_id=current_user.id,
    )

    if db_household is None:
        raise HTTPException(
            status_code=404,
            detail="Пользователь-владелец не найден",
        )

    return db_household


@app.get("/households", response_model=list[UserHouseholdResponse])
def list_my_households_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Возвращает домохозяйства текущего пользователя и его роль в каждом.

    Зачем нужен: главный экран интерфейса показывает, в каких домохозяйствах
    состоит пользователь и что он в них может делать.

    Запрос: GET /households с заголовком "Authorization: Bearer ...".
    Ответ:  [{"id": 1, "name": "Дом", "created_at": "2026-10-22T10:15:00Z",
              "role": "owner"}]
    Если пользователь пока ни в одном домохозяйстве, ответом будет пустой
    список [].
    """
    # current_user.id — id владельца токена, например 1. Передаём только его,
    # поэтому показываются только собственные домохозяйства.
    # Это тот же GET-путь /households, что и у POST, но с другим методом.
    return get_user_households_service(db=db, user_id=current_user.id)


@app.post(
    "/households/{household_id}/members",
    response_model=HouseholdMemberResponse,
    status_code=201,
)
def add_household_member_endpoint(
    household_id: int,
    member: HouseholdMemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_household_member(
        household_id=household_id,
        db=db,
        current_user=current_user,
        allowed_roles=("owner", "admin"),
    )
    try:
        return add_household_member_service(
            db=db,
            household_id=household_id,
            user_id=member.user_id,
        )

    except HouseholdNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Домохозяйство не найдено",
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Пользователь не найден",
        )

    except HouseholdMemberAlreadyExistsError:
        raise HTTPException(
            status_code=409,
            detail="Пользователь уже является членом этого домохозяйства",
        )


@app.get(
    "/households/{household_id}/members",
    response_model=list[HouseholdMemberDetailResponse],
)
def get_household_members_endpoint(
    household_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_household_member(
        household_id=household_id,
        db=db,
        current_user=current_user,
    )
    try:
        return get_household_members_service(
            db=db,
            household_id=household_id,
        )

    except HouseholdNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Household not found",
        )


@app.patch("/users/{user_id}", response_model=UserResponse,
    dependencies=[Depends(require_same_user)],)
def update_user_endpoint(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
):
    changes = user_data.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=422,
            detail="Provide at least one field to update",
        )

    nullable_fields = {"birth_date", "sex", "occupation"}

    invalid_null_fields = [
        field
        for field, value in changes.items()
        if value is None and field not in nullable_fields
    ]

    if invalid_null_fields:
        raise HTTPException(
            status_code=422,
            detail="These fields cannot be null: "
                   + ", ".join(invalid_null_fields),
        )

    db_user = update_user_service(
        db=db,
        user_id=user_id,
        changes=changes,
    )

    if db_user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    return db_user


@app.post(
    "/users/{user_id}/weight-records",
    response_model=WeightRecordResponse,
    status_code=201,
    dependencies=[Depends(require_same_user)],
)
def create_weight_record_endpoint(
    user_id: int,
    record: WeightRecordCreate,
    db: Session = Depends(get_db),
):
    try:
        return create_weight_record_service(
            db=db,
            user_id=user_id,
            record_data=record,
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )


@app.get(
    "/users/{user_id}/weight-records",
    response_model=list[WeightRecordResponse],
    dependencies=[Depends(require_same_user)],
)
def get_weight_records_endpoint(
    user_id: int,
    db: Session = Depends(get_db),
):
    try:
        return get_weight_records_service(
            db=db,
            user_id=user_id,
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )


@app.post(
    "/users/{user_id}/goals",
    response_model=GoalResponse,
    status_code=201,
    dependencies=[Depends(require_same_user)],
)
def create_goal_endpoint(
    user_id: int,
    goal_data: GoalCreate,
    db: Session = Depends(get_db),
):
    try:
        # Передаём создание цели сервисному слою
        return create_goal_service(
            db=db,
            user_id=user_id,
            goal_data=goal_data,
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )


@app.get(
    "/users/{user_id}/goals",
    response_model=list[GoalResponse],
    dependencies=[Depends(require_same_user)],
)
def get_user_goals_endpoint(
    user_id: int,
    db: Session = Depends(get_db),
):
    try:
        # Получаем цели указанного пользователя
        return get_user_goals_service(
            db=db,
            user_id=user_id,
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )


@app.patch(
    "/users/{user_id}/goals/{goal_id}",
    response_model=GoalResponse,
    dependencies=[Depends(require_same_user)],
)
def update_goal_endpoint(
    user_id: int,
    goal_id: int,
    goal_data: GoalUpdate,
    db: Session = Depends(get_db),
):
    # Получаем только явно переданные поля
    changes = goal_data.model_dump(exclude_unset=True)

    # Пустой запрос ничего не изменяет
    if not changes:
        raise HTTPException(
            status_code=422,
            detail="Provide at least one field to update",
        )

    # Эти поля разрешено очищать через null
    nullable_fields = {
        "target_weight_kg",
        "target_body_fat_percent",
        "desired_rate_kg_per_week",
        "target_date",
        "notes",
    }

    # Остальные поля должны иметь значения
    invalid_null_fields = [
        field
        for field, value in changes.items()
        if value is None and field not in nullable_fields
    ]

    if invalid_null_fields:
        raise HTTPException(
            status_code=422,
            detail="These fields cannot be null: "
            + ", ".join(invalid_null_fields),
        )

    try:
        return update_goal_service(
            db=db,
            user_id=user_id,
            goal_id=goal_id,
            changes=changes,
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    except GoalNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Goal not found for this user",
        )

    except InvalidGoalDatesError:
        raise HTTPException(
            status_code=422,
            detail="target_date cannot be earlier than start_date",
        )


@app.post(
    "/users/{user_id}/schedule-events",
    response_model=ScheduleEventResponse,
    status_code=201,
    dependencies=[Depends(require_same_user)],
)
def create_schedule_event_endpoint(
    user_id: int,
    event_data: ScheduleEventCreate,
    db: Session = Depends(get_db),
):
    try:
        return create_schedule_event_service(
            db=db,
            user_id=user_id,
            event_data=event_data,
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )


@app.get(
    "/users/{user_id}/schedule-events",
    response_model=list[ScheduleEventResponse],
    dependencies=[Depends(require_same_user)],
)
def get_schedule_events_endpoint(
    user_id: int,
    from_at: datetime,
    to_at: datetime,
    db: Session = Depends(get_db),
):
    # Проверяем, что обе даты содержат часовой пояс
    if from_at.utcoffset() is None or to_at.utcoffset() is None:
        raise HTTPException(
            status_code=422,
            detail="from_at and to_at must include a timezone offset",
        )

    # Проверяем корректность периода
    if to_at <= from_at:
        raise HTTPException(
            status_code=422,
            detail="to_at must be later than from_at",
        )

    try:
        return get_schedule_events_service(
            db=db,
            user_id=user_id,
            from_at=from_at,
            to_at=to_at,
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )


@app.post(
    "/users/{user_id}/training-sessions",
    response_model=TrainingSessionResponse,
    status_code=201,
    dependencies=[Depends(require_same_user)],
)
def create_training_session_endpoint(
    user_id: int,
    session_data: TrainingSessionCreate,
    db: Session = Depends(get_db),
):
    try:
        return create_training_session_service(
            db=db,
            user_id=user_id,
            session_data=session_data,
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    except ScheduleEventNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Schedule event not found for this user",
        )

    except ScheduleEventAlreadyLinkedError:
        raise HTTPException(
            status_code=409,
            detail="Schedule event is already linked to a training session",
        )


@app.get(
    "/users/{user_id}/training-sessions",
    response_model=list[TrainingSessionResponse],
    dependencies=[Depends(require_same_user)],
)
def get_training_sessions_endpoint(
    user_id: int,
    db: Session = Depends(get_db),
):
    try:
        return get_training_sessions_service(
            db=db,
            user_id=user_id,
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )


@app.post(
    "/users/{user_id}/training-sessions/{training_session_id}/workouts",
    response_model=WorkoutResponse,
    status_code=201,
    dependencies=[Depends(require_same_user)],
)
def create_workout_endpoint(
    user_id: int,
    training_session_id: int,
    workout_data: WorkoutCreate,
    db: Session = Depends(get_db),
):
    # Создаём блок тренировки через сервисный слой
    try:
        return create_workout(
            db=db,
            user_id=user_id,
            training_session_id=training_session_id,
            workout_data=workout_data,
        )

    except WorkoutSessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Тренировочная сессия не найдена у указанного пользователя",
        )

    except WorkoutTimeOutsideSessionError:
        raise HTTPException(
            status_code=422,
            detail="Время блока должно находиться внутри тренировочной сессии",
        )

    except WorkoutSaveError:
        raise HTTPException(
            status_code=500,
            detail="Не удалось сохранить блок тренировки",
        )


@app.get(
    "/users/{user_id}/training-sessions/{training_session_id}/workouts",
    response_model=list[WorkoutResponse],
    dependencies=[Depends(require_same_user)],
)
def list_training_session_workouts(
    user_id: int,
    training_session_id: int,
    db: Session = Depends(get_db),
):
    # Получаем блоки конкретной сессии через сервисный слой
    try:
        return get_workouts_for_training_session(
            db=db,
            user_id=user_id,
            training_session_id=training_session_id,
        )

    except WorkoutSessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Тренировочная сессия не найдена у указанного пользователя",
        )


@app.patch(
    "/users/{user_id}/training-sessions/{training_session_id}/workouts/{workout_id}",
    response_model=WorkoutResponse,
    dependencies=[Depends(require_same_user)],
)
def update_workout_endpoint(
    user_id: int,
    training_session_id: int,
    workout_id: int,
    workout_data: WorkoutUpdate,
    db: Session = Depends(get_db),
):
    # Изменяем блок через сервисный слой
    try:
        return update_workout(
            db=db,
            user_id=user_id,
            training_session_id=training_session_id,
            workout_id=workout_id,
            workout_data=workout_data,
        )

    except WorkoutSessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Тренировочная сессия не найдена у указанного пользователя",
        )

    except WorkoutNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Блок тренировки не найден в указанной сессии",
        )

    except WorkoutSaveError:
        raise HTTPException(
            status_code=500,
            detail="Не удалось сохранить изменения блока тренировки",
        )


@app.post(
    "/users/{user_id}/meal-entries",
    response_model=MealEntryResponse,
    status_code=201,
    dependencies=[Depends(require_same_user)],
)
def create_meal_entry_endpoint(
    user_id: int,
    meal_data: MealEntryCreate,
    db: Session = Depends(get_db),
):
    # Создаём запись через сервисный слой
    try:
        return create_meal_entry(
            db=db,
            user_id=user_id,
            meal_data=meal_data,
        )

    except MealEntryUserNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Пользователь не найден",
        )

    except MealEntrySaveError:
        raise HTTPException(
            status_code=500,
            detail="Не удалось сохранить запись о приёме пищи",
        )


@app.get(
    "/users/{user_id}/meal-entries",
    response_model=list[MealEntryResponse],
    dependencies=[Depends(require_same_user)],
)
def list_meal_entries_endpoint(
    user_id: int,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    db: Session = Depends(get_db),
):
    # Проверяем корректность временных границ
    if from_at is not None and (
        from_at.tzinfo is None or from_at.utcoffset() is None
    ):
        raise HTTPException(
            status_code=422,
            detail="from_at должен содержать часовой пояс",
        )

    if to_at is not None and (
        to_at.tzinfo is None or to_at.utcoffset() is None
    ):
        raise HTTPException(
            status_code=422,
            detail="to_at должен содержать часовой пояс",
        )

    if from_at is not None and to_at is not None and from_at >= to_at:
        raise HTTPException(
            status_code=422,
            detail="from_at должен быть раньше to_at",
        )

    # Получаем записи за заданный период
    try:
        return get_meal_entries(
            db=db,
            user_id=user_id,
            from_at=from_at,
            to_at=to_at,
        )

    except MealEntryUserNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Пользователь не найден",
        )


@app.get(
    "/users/{user_id}/nutrition/daily-summary",
    response_model=DailyNutritionSummary,
    dependencies=[Depends(require_same_user)],
)
def daily_nutrition_summary_endpoint(
    user_id: int,
    target_date: date,
    db: Session = Depends(get_db),
):
    # Получаем дневную сводку питания
    try:
        return get_daily_nutrition_summary(
            db=db,
            user_id=user_id,
            target_date=target_date,
        )

    except MealEntryUserNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Пользователь не найден",
        )


@app.get(
    "/users/{user_id}/nutrition/daily-entries",
    response_model=list[MealEntryResponse],
    dependencies=[Depends(require_same_user)],
)
def daily_meal_entries_endpoint(
    user_id: int,
    target_date: date,
    db: Session = Depends(get_db),
):
    """Приёмы пищи за один день по часовому поясу пользователя.

    Запрос: GET /users/1/nutrition/daily-entries?target_date=2026-10-23
    Ответ:  список MealEntryResponse по времени; пустой список, если записей нет.
    """
    try:
        return get_meal_entries_for_day(
            db=db,
            user_id=user_id,
            target_date=target_date,
        )
    except MealEntryUserNotFoundError:
        raise HTTPException(status_code=404, detail="Пользователь не найден")


@app.delete(
    "/users/{user_id}/meal-entries/{entry_id}",
    status_code=204,
    dependencies=[Depends(require_same_user)],
)
def delete_meal_entry_endpoint(
    user_id: int,
    entry_id: int,
    db: Session = Depends(get_db),
):
    """Удаляет запись о приёме пищи. Успех: 204 без тела; нет записи: 404."""
    try:
        delete_meal_entry(db=db, user_id=user_id, entry_id=entry_id)
    except MealEntryNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Запись о приёме пищи не найдена",
        )
    except MealEntrySaveError:
        raise HTTPException(
            status_code=500,
            detail="Не удалось удалить запись о приёме пищи",
        )


@app.delete(
    "/users/{user_id}/weight-records/{record_id}",
    status_code=204,
    dependencies=[Depends(require_same_user)],
)
def delete_weight_record_endpoint(
    user_id: int,
    record_id: int,
    db: Session = Depends(get_db),
):
    """Удаляет запись веса. Успех: 204 без тела; нет записи: 404."""
    try:
        delete_weight_record(db=db, user_id=user_id, record_id=record_id)
    except WeightRecordNotFoundError:
        raise HTTPException(status_code=404, detail="Запись веса не найдена")


@app.patch(
    "/users/{user_id}/training-sessions/{training_session_id}",
    response_model=TrainingSessionResponse,
    dependencies=[Depends(require_same_user)],
)
def update_training_session_endpoint(
    user_id: int,
    training_session_id: int,
    session_data: TrainingSessionUpdate,
    db: Session = Depends(get_db),
):
    """Меняет статус и/или заметки тренировочной сессии.

    Пример тела: {"status": "completed"}
    """
    # Только поля, которые клиент действительно передал
    changes = session_data.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=422,
            detail="Provide at least one field to update",
        )

    # Статус не может быть пустым; очищать через null можно только заметки
    if "status" in changes and changes["status"] is None:
        raise HTTPException(status_code=422, detail="status cannot be null")

    try:
        return update_training_session_service(
            db=db,
            user_id=user_id,
            training_session_id=training_session_id,
            changes=changes,
        )
    except TrainingSessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Тренировочная сессия не найдена у указанного пользователя",
        )


@app.delete(
    "/users/{user_id}/goals/{goal_id}",
    status_code=204,
    dependencies=[Depends(require_same_user)],
)
def delete_goal_endpoint(
    user_id: int,
    goal_id: int,
    db: Session = Depends(get_db),
):
    """Удаляет цель навсегда. Успех: 204 без тела; нет цели: 404."""
    try:
        delete_goal(db=db, user_id=user_id, goal_id=goal_id)
    except GoalNotFoundError:
        raise HTTPException(status_code=404, detail="Цель не найдена")


@app.delete(
    "/users/{user_id}/training-sessions/{training_session_id}",
    status_code=204,
    dependencies=[Depends(require_same_user)],
)
def delete_training_session_endpoint(
    user_id: int,
    training_session_id: int,
    db: Session = Depends(get_db),
):
    """Удаляет тренировочную сессию вместе с её блоками. Успех: 204."""
    try:
        delete_training_session(
            db=db,
            user_id=user_id,
            training_session_id=training_session_id,
        )
    except TrainingSessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Тренировочная сессия не найдена у указанного пользователя",
        )


@app.delete(
    "/users/{user_id}/training-sessions/{training_session_id}/workouts/{workout_id}",
    status_code=204,
    dependencies=[Depends(require_same_user)],
)
def delete_workout_endpoint(
    user_id: int,
    training_session_id: int,
    workout_id: int,
    db: Session = Depends(get_db),
):
    """Удаляет один блок тренировки. Успех: 204 без тела."""
    try:
        delete_workout(
            db=db,
            user_id=user_id,
            training_session_id=training_session_id,
            workout_id=workout_id,
        )
    except WorkoutSessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Тренировочная сессия не найдена у указанного пользователя",
        )
    except WorkoutNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Блок тренировки не найден в указанной сессии",
        )
    except WorkoutSaveError:
        raise HTTPException(
            status_code=500,
            detail="Не удалось удалить блок тренировки",
        )