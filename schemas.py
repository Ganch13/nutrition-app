from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from datetime import datetime, date
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from decimal import Decimal


# Допустимые значения поля sex
Sex = Literal["male", "female", "unspecified"]


def validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(
            "Use a valid IANA timezone, for example Europe/Moscow or UTC"
        ) from exc

    return value


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    birth_date: date | None = None
    sex: Sex | None = None
    height_cm: int = Field(gt=0, le=300)
    occupation: str | None = Field(default=None, max_length=100)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, value: str) -> str:
        return validate_timezone(value)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    age: int | None
    birth_date: date | None
    sex: Sex | None
    height_cm: int
    occupation: str | None
    timezone: str
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def calculate_age(cls, value):
        if isinstance(value, dict):
            data = dict(value)
        else:
            field_names = (
                "id",
                "name",
                "age",
                "birth_date",
                "sex",
                "height_cm",
                "occupation",
                "timezone",
                "created_at",
            )
            data = {
                field: getattr(value, field, None)
                for field in field_names
            }

        birth_date = data.get("birth_date")

        if birth_date is not None:
            timezone_name = data.get("timezone") or "UTC"
            today = datetime.now(ZoneInfo(timezone_name)).date()

            data["age"] = (
                today.year
                - birth_date.year
                - (
                    (today.month, today.day)
                    < (birth_date.month, birth_date.day)
                )
            )
        else:
            # Временно сохраняем возраст старых записей,
            # в которых ещё нет даты рождения.
            data.setdefault("age", None)

        return data


class UserUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    birth_date: date | None = None
    sex: Sex | None = None
    height_cm: int | None = Field(
        default=None,
        gt=0,
        le=300,
    )
    occupation: str | None = Field(
        default=None,
        max_length=100,
    )
    timezone: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
    )

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return validate_timezone(value)


class HouseholdCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    owner_user_id: int = Field(gt=0)


class HouseholdResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


class HouseholdMemberCreate(BaseModel):
    user_id: int = Field(gt=0)


class HouseholdMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    household_id: int
    user_id: int
    role: str
    joined_at: datetime


class WeightRecordCreate(BaseModel):
    measurement_date: date
    weight_kg: Decimal = Field(
        gt=0,
        max_digits=5,
        decimal_places=2,
    )
    body_fat_percent: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
        max_digits=5,
        decimal_places=2,
    )
    notes: str | None = None


class WeightRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    measurement_date: date
    weight_kg: Decimal
    body_fat_percent: Decimal | None
    notes: str | None
    created_at: datetime


# Допустимые типы целей
GoalType = Literal[
    "fat_loss",
    "muscle_gain",
    "weight_maintenance",
    "performance",
    "general_health",
]

# Допустимые статусы цели
GoalStatus = Literal[
    "active",
    "completed",
    "paused",
    "cancelled",
]


class GoalCreate(BaseModel):
    # Тип цели: снижение веса, набор мышц и т. д.
    goal_type: GoalType

    # Приоритет от 1 (самый высокий) до 5
    priority: int = Field(default=3, ge=1, le=5)

    # Целевой вес в килограммах
    target_weight_kg: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=5,
        decimal_places=2,
    )

    # Целевой процент жира
    target_body_fat_percent: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
        max_digits=5,
        decimal_places=2,
    )

    # Желаемая скорость изменения веса в кг за неделю
    desired_rate_kg_per_week: Decimal | None = Field(
        default=None,
        gt=0,
        le=5,
        max_digits=4,
        decimal_places=2,
    )

    # Дата начала цели
    start_date: date

    # Планируемая дата достижения цели
    target_date: date | None = None

    # Дополнительная информация о цели
    notes: str | None = None

    @model_validator(mode="after")
    def validate_target_date(self):
        # Дата достижения не может быть раньше даты начала
        if (
            self.target_date is not None
            and self.target_date < self.start_date
        ):
            raise ValueError(
                "target_date cannot be earlier than start_date"
            )

        return self



class GoalUpdate(BaseModel):
    # Тип цели: снижение веса, набор мышц и т. д.
    goal_type: GoalType | None = None

    # Приоритет от 1 до 5
    priority: int | None = Field(default=None, ge=1, le=5)

    # Целевой вес в килограммах
    target_weight_kg: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=5,
        decimal_places=2,
    )

    # Целевой процент жира
    target_body_fat_percent: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
        max_digits=5,
        decimal_places=2,
    )

    # Желаемое изменение веса в кг за неделю
    desired_rate_kg_per_week: Decimal | None = Field(
        default=None,
        gt=0,
        le=5,
        max_digits=4,
        decimal_places=2,
    )

    # Дата начала цели
    start_date: date | None = None

    # Планируемая дата завершения
    target_date: date | None = None

    # Новый статус цели
    status: GoalStatus | None = None

    # Дополнительные сведения
    notes: str | None = None



class GoalResponse(BaseModel):
    # Позволяет формировать ответ из объекта SQLAlchemy
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int

    # Основные параметры цели
    goal_type: GoalType
    priority: int
    target_weight_kg: Decimal | None
    target_body_fat_percent: Decimal | None
    desired_rate_kg_per_week: Decimal | None

    # Даты и состояние цели
    start_date: date
    target_date: date | None
    status: GoalStatus

    # Дополнительная информация и дата создания
    notes: str | None
    created_at: datetime


# Допустимые типы событий расписания
ScheduleEventType = Literal[
    "sleep",
    "work",
    "meal",
    "workout",
    "personal",
    "other",
]


class ScheduleEventCreate(BaseModel):
    # Тип события: сон, работа, приём пищи и т. д.
    event_type: ScheduleEventType

    # Название события
    title: str = Field(min_length=1, max_length=150)

    # Момент начала события с часовым поясом
    start_at: datetime

    # Момент окончания события с часовым поясом
    end_at: datetime

    # Место проведения, если указано
    location: str | None = Field(default=None, max_length=200)

    # Дополнительные сведения
    notes: str | None = None

    @model_validator(mode="after")
    def validate_time_range(self):
        # Проверяем наличие часового пояса у обеих дат
        if (
            self.start_at.utcoffset() is None
            or self.end_at.utcoffset() is None
        ):
            raise ValueError(
                "start_at and end_at must include a timezone offset"
            )

        # Окончание должно быть позже начала
        if self.end_at <= self.start_at:
            raise ValueError(
                "end_at must be later than start_at"
            )

        return self


class ScheduleEventResponse(BaseModel):
    # Позволяет формировать ответ из объекта SQLAlchemy
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int

    # Основные поля события
    event_type: ScheduleEventType
    title: str
    start_at: datetime
    end_at: datetime

    # Дополнительные данные
    location: str | None
    notes: str | None
    created_at: datetime


# Допустимые статусы тренировочной сессии
TrainingSessionStatus = Literal[
    "planned",
    "completed",
    "skipped",
    "cancelled",
]


class TrainingSessionCreate(BaseModel):
    # Связанное событие расписания; можно не указывать
    schedule_event_id: int | None = Field(default=None, gt=0)

    # Название тренировки
    name: str = Field(min_length=1, max_length=150)

    # Время начала тренировки с часовым поясом
    start_at: datetime

    # Время окончания тренировки с часовым поясом
    end_at: datetime

    # Статус: по умолчанию тренировка запланирована
    status: TrainingSessionStatus = "planned"

    # Дополнительные сведения
    notes: str | None = None

    @model_validator(mode="after")
    def validate_session(self):
        # Обе даты должны содержать информацию о часовом поясе
        if (
            self.start_at.utcoffset() is None
            or self.end_at.utcoffset() is None
        ):
            raise ValueError(
                "start_at and end_at must include a timezone offset"
            )

        # Окончание должно быть позже начала
        if self.end_at <= self.start_at:
            raise ValueError(
                "end_at must be later than start_at"
            )

        return self


class TrainingSessionResponse(BaseModel):
    # Формируем ответ из объекта SQLAlchemy
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    schedule_event_id: int | None

    # Основные данные тренировки
    name: str
    start_at: datetime
    end_at: datetime
    status: TrainingSessionStatus

    # Дополнительные данные
    notes: str | None
    created_at: datetime