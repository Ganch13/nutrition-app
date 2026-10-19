from fastapi import FastAPI, HTTPException, Depends
from schemas import TrainingSessionCreate, TrainingSessionResponse, ScheduleEventCreate, ScheduleEventResponse, GoalUpdate, GoalCreate, GoalResponse, WeightRecordCreate, WeightRecordResponse, UserUpdate, HouseholdMemberCreate, HouseholdMemberResponse,HouseholdCreate, HouseholdResponse, UserCreate, UserResponse
from database import get_db
from sqlalchemy.orm import Session
from services import ( ScheduleEventAlreadyLinkedError, ScheduleEventNotFoundError, create_training_session as create_training_session_service, get_training_sessions as get_training_sessions_service,create_schedule_event as create_schedule_event_service, get_schedule_events as get_schedule_events_service, GoalNotFoundError, InvalidGoalDatesError,
                       update_goal as update_goal_service, create_goal as create_goal_service, get_user_goals as get_user_goals_service, create_weight_record as create_weight_record_service,
                      get_weight_records as get_weight_records_service, update_user as update_user_service, get_household_members as get_household_members_service,
                      create_user as create_user_service, get_user as get_user_service, create_household as create_household_service, HouseholdMemberAlreadyExistsError,
                      HouseholdNotFoundError, UserNotFoundError, add_household_member as add_household_member_service)
from datetime import datetime


app = FastAPI()




@app.get("/hello")
def hello():
    print("Hello World")
    return {"message": "Hello Daniil"}

@app.get("/users/{user_id}", response_model=UserResponse)
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


@app.post("/users", response_model=UserResponse)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db)
):
    return create_user_service(db, user)

@app.post(
    "/households",
    response_model=HouseholdResponse,
    status_code=201,
)
def create_household_endpoint(
    household: HouseholdCreate,
    db: Session = Depends(get_db),
):
    db_household = create_household_service(
        db=db,
        name=household.name,
        owner_user_id=household.owner_user_id,
    )

    if db_household is None:
        raise HTTPException(
            status_code=404,
            detail="Owner user not found",
        )

    return db_household


@app.post(
    "/households/{household_id}/members",
    response_model=HouseholdMemberResponse,
    status_code=201,
)
def add_household_member_endpoint(
    household_id: int,
    member: HouseholdMemberCreate,
    db: Session = Depends(get_db),
):
    try:
        return add_household_member_service(
            db=db,
            household_id=household_id,
            user_id=member.user_id,
        )

    except HouseholdNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Household not found",
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    except HouseholdMemberAlreadyExistsError:
        raise HTTPException(
            status_code=409,
            detail="User is already a member of this household",
        )


@app.get(
    "/households/{household_id}/members",
    response_model=list[HouseholdMemberResponse],
)
def get_household_members_endpoint(
    household_id: int,
    db: Session = Depends(get_db),
):
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


@app.patch("/users/{user_id}", response_model=UserResponse)
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