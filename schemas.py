from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)
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


class RegisterRequest(BaseModel):
    """Данные для регистрации нового пользователя."""

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    height_cm: int = Field(gt=0, le=300)
    birth_date: date | None = None
    sex: Sex | None = None
    occupation: str | None = Field(default=None, max_length=100)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, value: str) -> str:
        """Проверяет, что timezone — существующее название IANA.

        Когда вызывается: Pydantic запускает метод для поля timezone после
        проверки, что это строка допустимой длины (1–64 символа).

        value — присланное название, например "Europe/Berlin" или "Not/AZone".
        Если зона существует, возвращаем то же значение: "Europe/Berlin".
        Если не существует, validate_timezone выбросит ValueError с сообщением
        "Use a valid IANA timezone...", а Pydantic превратит его в ответ 422.
        """
        # validate_timezone определена выше в этом же файле, её уже использует UserCreate.
        # Она пытается создать ZoneInfo(value), и при неудаче выбрасывает ValueError.
        return validate_timezone(value)


class LoginRequest(BaseModel):
    """Данные для входа существующего пользователя."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)



class TokenResponse(BaseModel):
    """Ответ сервера после успешного входа."""

    access_token: str
    token_type: str = "bearer"

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


class UserHouseholdResponse(BaseModel):
    """Домохозяйство вместе с ролью текущего пользователя в нём.

    Используется в GET /households. Интерфейсу нужна роль, чтобы решить,
    показывать ли кнопку «Добавить участника» (её видят только owner и admin).

    Пример данных:
        {"id": 1, "name": "Дом", "created_at": "2026-10-22T10:15:00Z",
         "role": "owner"}
    """

    # Идентификатор домохозяйства, например 1
    id: int

    # Название домохозяйства, например "Дом"
    name: str

    # Дата и время создания, например 2026-10-22 10:15:00 в UTC
    created_at: datetime

    # Роль текущего пользователя в этом домохозяйстве. Допустимые значения
    # те же, что в CheckConstraint таблицы household_members.
    role: Literal["owner", "admin", "member"]


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


class WorkoutCreate(BaseModel):
    # Название блока тренировки
    name: str = Field(min_length=1, max_length=150)

    # Тип нагрузки
    load_type: Literal["strength", "cardio", "mixed", "other"]

    # Планируемая интенсивность
    planned_intensity: Literal["low", "moderate", "high"]

    # Фактическая интенсивность; заполняется после тренировки
    actual_intensity: Literal["low", "moderate", "high"] | None = None

    # Начало и окончание блока
    start_at: datetime
    end_at: datetime

    # Дополнительные заметки
    notes: str | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        # Не разрешаем даты без часового пояса
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Дата и время должны содержать часовой пояс")
        return value

    @model_validator(mode="after")
    def validate_time_range(self):
        # Окончание должно быть позже начала
        if self.end_at <= self.start_at:
            raise ValueError("Окончание должно быть позже начала")
        return self


class WorkoutResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    # Идентификатор блока
    id: int

    # Идентификатор тренировочной сессии
    training_session_id: int

    # Название блока
    name: str

    # Тип нагрузки
    load_type: str

    # Планируемая интенсивность
    planned_intensity: str

    # Фактическая интенсивность
    actual_intensity: str | None

    # Время начала и окончания
    start_at: datetime
    end_at: datetime

    # Заметки
    notes: str | None

    # Время создания записи в базе данных
    created_at: datetime




class WorkoutUpdate(BaseModel):
    # Фактическая интенсивность после выполнения
    actual_intensity: Literal["low", "moderate", "high"] | None = None

    # Заметки по результатам выполнения
    notes: str | None = None


class MealEntryCreate(BaseModel):
    # Дата и время приёма пищи
    eaten_at: datetime

    # Тип приёма пищи
    meal_type: Literal["breakfast", "lunch", "dinner", "snack", "other"]

    # Название или описание еды
    description: str = Field(min_length=1, max_length=250)

    # Калорийность
    calories: Decimal = Field(ge=0, max_digits=8, decimal_places=2)

    # Белки, жиры и углеводы в граммах
    protein_g: Decimal = Field(ge=0, max_digits=8, decimal_places=2)
    fat_g: Decimal = Field(ge=0, max_digits=8, decimal_places=2)
    carbs_g: Decimal = Field(ge=0, max_digits=8, decimal_places=2)

    # Дополнительные заметки
    notes: str | None = None

    @field_validator("eaten_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        # Не принимаем дату без часового пояса
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Дата и время должны содержать часовой пояс")
        return value


class MealEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # Идентификатор записи
    id: int

    # Владелец записи
    user_id: int

    # Дата и время приёма пищи
    eaten_at: datetime

    # Тип приёма пищи
    meal_type: str

    # Название еды
    description: str

    # Калорийность и БЖУ
    calories: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carbs_g: Decimal

    # Дополнительные заметки
    notes: str | None

    # Время создания записи
    created_at: datetime



class DailyNutritionSummary(BaseModel):
    # День, за который рассчитаны итоги
    date: date

    # Идентификатор пользователя
    user_id: int

    # Количество записей о приёмах пищи
    entries_count: int

    # Общие калории и БЖУ за день
    calories: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carbs_g: Decimal

    # Настройки сериализации Pydantic 2 здесь не требуются,
    # поскольку схема создаётся из обычных значений.