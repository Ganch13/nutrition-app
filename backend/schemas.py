from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)
from datetime import datetime, date, time
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

# Блоки главной страницы, которые можно скрыть: деньги, финансовая цель, питание, тренировка, вес
HomeBlock = Literal["money", "finance_goal", "nutrition", "training", "weight"]


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
    # Скрытые блоки главной страницы, например ["money", "weight"]
    home_hidden_blocks: list[HomeBlock] = []
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
                "home_hidden_blocks",
                "created_at",
            )
            data = {
                field: getattr(value, field, None)
                for field in field_names
            }

        # Пока список не загружен из базы (или его нет в словаре), блоки не скрыты
        data["home_hidden_blocks"] = data.get("home_hidden_blocks") or []

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
    # Полный список скрытых блоков главной: [] — показать всё, ["weight"] — скрыть вес
    home_hidden_blocks: list[HomeBlock] | None = Field(default=None, max_length=5)

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return validate_timezone(value)

    @field_validator("home_hidden_blocks")
    @classmethod
    def unique_blocks(cls, value: list[str] | None) -> list[str] | None:
        # Повторы убираем, порядок не важен: ["weight", "weight"] → ["weight"]
        return None if value is None else sorted(set(value))


class HouseholdCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class HouseholdResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


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

class HouseholdMemberDetailResponse(BaseModel):
    """Участник домохозяйства с именем (для экрана «Семья»).

    Пример: {"household_id": 1, "user_id": 2, "name": "Леся", "role": "member",
             "joined_at": "2026-10-26T10:05:00Z"}
    Email и другие данные профиля намеренно не отдаём: участникам нужны только имена.
    """

    model_config = ConfigDict(from_attributes=True)

    household_id: int
    user_id: int
    name: str
    role: Literal["owner", "admin", "member"]
    joined_at: datetime


class HouseholdInviteResponse(BaseModel):
    """Код приглашения. Пример: {"id": 1, "household_id": 1, "code": "K7M29QXP",
    "created_at": "2026-10-26T10:00:00Z", "expires_at": "2026-11-02T10:00:00Z"}"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    household_id: int
    code: str
    created_at: datetime
    expires_at: datetime


class HouseholdJoinRequest(BaseModel):
    """Тело запроса POST /households/join. Пример: {"code": "K7M2-9QXP"}.
    Регистр и дефис не важны: код нормализует сервис."""

    code: str = Field(min_length=1, max_length=64)


class HouseholdMemberRoleUpdate(BaseModel):
    """Тело запроса PATCH .../members/{user_id}. Пример: {"role": "admin"}.
    Роль «owner» назначить нельзя: владелец один, передачу владения сделаем позже."""

    role: Literal["admin", "member"]



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

    # «Внутри этого блока могут быть другие события» (например, «Работа» с обедом внутри)
    is_container: bool = False

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

    # Идентификатор серии, если событие повторяющееся (иначе None)
    series_id: str | None = None
    # Блок, внутри которого могут быть другие события
    is_container: bool = False
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

    # Объединить с другим блоком этой сессии в суперсет. Тогда блоки могут
    # пересекаться по времени. Пример: 5 (id блока «Жим лёжа»). Без значения
    # новый блок обязан начинаться не раньше окончания предыдущего.
    superset_with_workout_id: int | None = Field(default=None, gt=0)

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

    # Номер суперсета (None — обычный блок) и время отметки «Выполнил»
    superset_group: int | None = None
    completed_at: datetime | None = None

    # Время создания записи в базе данных
    created_at: datetime




class WorkoutUpdate(BaseModel):
    # Фактическая интенсивность после выполнения
    actual_intensity: Literal["low", "moderate", "high"] | None = None

    # Заметки по результатам выполнения
    notes: str | None = None

    # Кнопка «Выполнил упражнение»: True отмечает блок выполненным,
    # False снимает отметку. Если фактическая интенсивность не указана,
    # при True она берётся равной плановой.
    completed: bool | None = None


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

    # Продукт справочника и масса, если запись создана «из справочника»
    food_id: int | None = None
    amount_g: Decimal | None = None

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


class TrainingSessionUpdate(BaseModel):
    """Изменение тренировочной сессии: статус и заметки.

    Пример тела запроса: {"status": "completed"}
    Время и название менять нельзя; передавать можно любое из двух полей.
    """

    # Новый статус: planned, completed, skipped или cancelled
    status: TrainingSessionStatus | None = None

    # Новые заметки; null очищает заметки
    notes: str | None = None


# ---------- Финансы ----------

# Вид книги: личная или семейная
LedgerKind = Literal["personal", "household"]

# Тип категории и операции: расход или доход
FinanceKind = Literal["expense", "income"]


class LedgerCreate(BaseModel):
    """Создание финансовой книги.

    Примеры тела запроса:
        {"kind": "personal", "currency": "EUR"}
        {"kind": "household", "household_id": 1, "currency": "EUR"}
    """

    kind: LedgerKind

    # Обязателен для семейной книги и запрещён для личной
    household_id: int | None = Field(default=None, gt=0)

    # Код валюты из трёх заглавных букв
    currency: str = Field(pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def validate_owner(self):
        if self.kind == "household" and self.household_id is None:
            raise ValueError("household_id is required for a household ledger")

        if self.kind == "personal" and self.household_id is not None:
            raise ValueError("household_id must not be set for a personal ledger")

        return self


class LedgerResponse(BaseModel):
    """Книга и права текущего пользователя в ней."""

    id: int
    kind: LedgerKind
    household_id: int | None
    # Название домохозяйства для семейной книги
    household_name: str | None
    currency: str
    # True, если пользователь может управлять категориями и лимитами
    can_manage: bool
    # Как считается бюджетный период: calendar (месяц) или income (от дохода до дохода)
    cycle_mode: Literal["calendar", "income"] = "calendar"


class FinanceCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: FinanceKind

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        # Убираем пробелы по краям; название из одних пробелов не допускаем
        value = value.strip()

        if not value:
            raise ValueError("Category name must not be empty")

        return value


class FinanceCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ledger_id: int
    name: str
    kind: FinanceKind


class FinanceTransactionCreate(BaseModel):
    """Новая операция, например:
    {"category_id": 3, "amount": 120.5, "occurred_on": "2026-10-26", "description": "Магазин"}
    Расход на цель (накопление, долг, кредит этой же книги):
    {"category_id": 9, "amount": 5000, "occurred_on": "2026-10-28", "goal_id": 1}
    """

    category_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    occurred_on: date
    description: str | None = Field(default=None, max_length=250)
    # Цель, к которой отнесён расход: сервер сам создаст запись в её истории на ту же сумму
    goal_id: int | None = Field(default=None, gt=0)


class FinanceTransactionUpdate(BaseModel):
    """Изменение операции: передаются только меняемые поля.

    Примеры: {"amount": 3000}; {"goal_id": 2} (перенести на другую цель); {"goal_id": null} (отвязать от цели);
    {"description": null} (очистить описание). Запись в цели пересчитывается вместе с операцией.
    """

    category_id: int | None = Field(default=None, gt=0)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    occurred_on: date | None = None
    description: str | None = Field(default=None, max_length=250)
    goal_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_required(self):
        # Сумму, дату и категорию очистить нельзя: у операции они обязательны
        for field in ("category_id", "amount", "occurred_on"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"Поле {field} нельзя очистить")
        return self


class FinanceTransactionResponse(BaseModel):
    id: int
    ledger_id: int
    category_id: int
    category_name: str
    kind: FinanceKind
    amount: Decimal
    occurred_on: date
    description: str | None
    # None, если автор удалил аккаунт (в интерфейсе подпись «Удалённый пользователь»)
    created_by_user_id: int | None
    created_by_name: str
    created_at: datetime
    # Цель, к которой отнесён расход, например 3 и "Отпуск"; None — без цели
    goal_id: int | None = None
    goal_name: str | None = None
    # Сводка, строкой которой является операция, и её период («Сводка 20–26 окт»); None — обычная операция
    summary_id: int | None = None
    summary_start: date | None = None
    summary_end: date | None = None


class ExpenseSummaryLine(BaseModel):
    """Строка сводки: категория расходов, сумма и (необязательно) цель. Пример: {"category_id": 3, "amount": 8000}."""

    category_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    goal_id: int | None = Field(default=None, gt=0)


class ExpenseSummaryCheck(BaseModel):
    """Сводка для сверки: период и строки. Пример:
    {"period_start": "2026-10-20", "period_end": "2026-10-26",
     "lines": [{"category_id": 3, "amount": 8000}, {"category_id": 5, "amount": 1200}]}
    """

    period_start: date
    period_end: date
    lines: list[ExpenseSummaryLine] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_start > self.period_end:
            raise ValueError("Начало периода позже конца")
        if (self.period_end - self.period_start).days > 366:
            raise ValueError("Сводка — не больше чем за год")
        return self


class ExpenseSummaryCreate(ExpenseSummaryCheck):
    """Сводка к сохранению. mode — ответ из окна сверки, если за период уже есть расходы:
      "add" — добавить как дополнение (ничего не удалять);
      "replace" — это повтор: удалить ровно replace_ids (операции, показанные при сверке) и записать сводку.
    Без пересечений mode не нужен. Пример: {..., "mode": "replace", "replace_ids": [12, 15], "note": "Чеки"}
    """

    mode: Literal["add", "replace"] | None = None
    replace_ids: list[int] = Field(default_factory=list, max_length=500)
    note: str | None = Field(default=None, max_length=250)

    @model_validator(mode="after")
    def validate_replace(self):
        if self.mode == "replace" and not self.replace_ids:
            raise ValueError("Для замены нужен список заменяемых операций (replace_ids)")
        if self.mode != "replace" and self.replace_ids:
            raise ValueError("replace_ids передаются только вместе с mode=replace")
        return self


class ExpenseSummaryMatch(BaseModel):
    """Уже записанный расход за период, который совпадает с категорией сводки."""

    transaction_id: int
    occurred_on: date
    category_id: int
    category_name: str
    amount: Decimal
    description: str | None
    # Если это строка прежней сводки — её id (повторно внесённая сводка тоже считается повтором)
    summary_id: int | None


class ExpenseSummaryCheckResponse(BaseModel):
    """Итог сверки. Пример: {"summary_total": "9200.00", "existing_total": "6400.00", "existing_count": 3,
    "matches": [...]} — интерфейс спрашивает «Это дополнение или повтор?». Пустой matches — пересечений нет."""

    period_start: date
    period_end: date
    summary_total: Decimal
    existing_total: Decimal
    existing_count: int
    matches: list[ExpenseSummaryMatch]


class ExpenseSummaryResponse(BaseModel):
    """Сохранённая сводка со строками (операциями)."""

    id: int
    ledger_id: int
    period_start: date
    period_end: date
    note: str | None
    total: Decimal
    created_by_user_id: int | None
    created_by_name: str
    created_at: datetime
    lines: list[FinanceTransactionResponse]
    # Сколько операций удалено при замене («повтор»); 0 — ничего не удалялось
    replaced_count: int = 0


class FinanceBudgetSet(BaseModel):
    """Лимит на категорию. Значение null (или отсутствие поля) убирает лимит."""

    monthly_limit: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)


class CategorySummary(BaseModel):
    """Итог по категории за месяц и её лимит."""

    category_id: int
    name: str
    kind: FinanceKind
    total: Decimal
    budget_limit: Decimal | None


class FinanceSummaryResponse(BaseModel):
    """Сводка за месяц."""

    ledger_id: int
    month: str
    currency: str
    income: Decimal
    expense: Decimal
    balance: Decimal
    categories: list[CategorySummary]


# ---------------------------------------------------------------------------
# Шаг 64. Расписание: изменение событий, повторяющиеся серии, недельный вид
# ---------------------------------------------------------------------------


class ScheduleEventUpdate(BaseModel):
    """Частичное изменение события: передаются только те поля, что меняются.

    Пример тела: {"title": "Работа (удалённо)", "location": "Дома"}
    """

    event_type: ScheduleEventType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=150)
    start_at: datetime | None = None
    end_at: datetime | None = None
    location: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    is_container: bool | None = None

    @model_validator(mode="after")
    def validate_update(self):
        # Обязательные поля нельзя «обнулить» значением null
        for name in ("event_type", "title", "start_at", "end_at", "is_container"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"Поле {name} нельзя очистить")

        # Даты без часового пояса не принимаем
        for value in (self.start_at, self.end_at):
            if value is not None and value.utcoffset() is None:
                raise ValueError("Дата и время должны содержать часовой пояс")

        # Если пришли обе даты, проверяем порядок. Если одна — сервис сверит с сохранённой.
        if (
            self.start_at is not None
            and self.end_at is not None
            and self.end_at <= self.start_at
        ):
            raise ValueError("Окончание должно быть позже начала")
        return self


class ScheduleSeriesCreate(BaseModel):
    """Повторяющееся по дням недели событие, например «Работа пн–пт 09:00–18:00».

    Пример тела:
    {"event_type": "work", "title": "Работа", "weekdays": [0,1,2,3,4],
     "start_time": "09:00", "end_time": "18:00", "from_date": "2026-10-26",
     "weeks": 4, "location": "Офис"}
    Дни недели: 0 — понедельник … 6 — воскресенье. Если end_time не позже
    start_time, событие заканчивается на следующий день (сон 23:00–07:00).
    """

    event_type: ScheduleEventType
    title: str = Field(min_length=1, max_length=150)
    weekdays: list[int] = Field(min_length=1, max_length=7)
    start_time: time
    end_time: time
    from_date: date
    weeks: int = Field(ge=1, le=26)
    location: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    # Каждое событие серии — блок, внутри которого могут быть другие события
    is_container: bool = False

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("Дни недели задаются числами от 0 (пн) до 6 (вс)")
        if len(set(value)) != len(value):
            raise ValueError("Дни недели не должны повторяться")
        return sorted(value)

    @model_validator(mode="after")
    def validate_times(self):
        if self.start_time == self.end_time:
            raise ValueError("Начало и окончание не могут совпадать")
        if self.start_time.tzinfo is not None or self.end_time.tzinfo is not None:
            raise ValueError("Время задаётся без часового пояса, например 09:00")
        return self


class ScheduleSeriesResponse(BaseModel):
    series_id: str
    events: list[ScheduleEventResponse]


class ScheduleItemRef(BaseModel):
    # Краткая ссылка на элемент недельного вида
    kind: Literal["event", "training"]
    id: int
    title: str


class ScheduleItem(BaseModel):
    """Элемент недельного расписания: событие или тренировка."""

    kind: Literal["event", "training"]
    id: int
    title: str
    # Для события — его тип (work, sleep…), для тренировки — "workout"
    category: str
    start_at: datetime
    end_at: datetime
    location: str | None = None
    # Только у тренировок: planned, completed, skipped, cancelled
    status: str | None = None
    series_id: str | None = None
    # Только у событий: блок, внутри которого могут быть другие события
    is_container: bool = False
    # id события-контейнера, внутрь которого целиком попадает этот элемент; иначе None
    parent_id: int | None = None


class ScheduleConflict(BaseModel):
    # Два элемента, пересекающиеся по времени
    first: ScheduleItemRef
    second: ScheduleItemRef


class ScheduleWeekResponse(BaseModel):
    start: date
    end: date
    timezone: str
    items: list[ScheduleItem]
    conflicts: list[ScheduleConflict]


# ---------------------------------------------------------------------------
# Шаг 65. Справочник продуктов
# ---------------------------------------------------------------------------

FoodCategory = Literal[
    "meat", "fish", "eggs", "dairy", "grains", "bakery", "vegetables", "fruits",
    "legumes", "nuts", "fats", "sweets", "drinks", "sauces", "supplements", "other",
]


class FoodCreate(BaseModel):
    """Свой продукт. Значения — на 100 г.

    Пример: {"name": "Творог Простоквашино 5%", "category": "dairy",
             "calories_per_100g": 121, "protein_per_100g": 17, "fat_per_100g": 5,
             "carbs_per_100g": 1.8, "serving_name": "1 пачка", "serving_grams": 200}
    Чтобы продукт видела вся семья, добавьте "household_id": 1.
    """

    name: str = Field(min_length=1, max_length=150)
    category: FoodCategory = "other"
    calories_per_100g: Decimal = Field(ge=0, le=900, max_digits=7, decimal_places=2)
    protein_per_100g: Decimal = Field(ge=0, le=100, max_digits=6, decimal_places=2)
    fat_per_100g: Decimal = Field(ge=0, le=100, max_digits=6, decimal_places=2)
    carbs_per_100g: Decimal = Field(ge=0, le=100, max_digits=6, decimal_places=2)
    serving_name: str | None = Field(default=None, min_length=1, max_length=40)
    serving_grams: Decimal | None = Field(default=None, gt=0, le=5000, max_digits=7, decimal_places=2)
    household_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_food(self):
        if self.protein_per_100g + self.fat_per_100g + self.carbs_per_100g > Decimal("100.5"):
            raise ValueError("Сумма белков, жиров и углеводов на 100 г не может превышать 100 г")
        if (self.serving_name is None) != (self.serving_grams is None):
            raise ValueError("Название порции и её масса задаются вместе")
        return self


class FoodUpdate(BaseModel):
    """Частичное изменение продукта; передаются только меняемые поля."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    category: FoodCategory | None = None
    calories_per_100g: Decimal | None = Field(default=None, ge=0, le=900, max_digits=7, decimal_places=2)
    protein_per_100g: Decimal | None = Field(default=None, ge=0, le=100, max_digits=6, decimal_places=2)
    fat_per_100g: Decimal | None = Field(default=None, ge=0, le=100, max_digits=6, decimal_places=2)
    carbs_per_100g: Decimal | None = Field(default=None, ge=0, le=100, max_digits=6, decimal_places=2)
    serving_name: str | None = Field(default=None, min_length=1, max_length=40)
    serving_grams: Decimal | None = Field(default=None, gt=0, le=5000, max_digits=7, decimal_places=2)

    @model_validator(mode="after")
    def validate_update(self):
        for name in ("name", "category", "calories_per_100g", "protein_per_100g", "fat_per_100g", "carbs_per_100g"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"Поле {name} нельзя очистить")
        return self


class FoodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: FoodCategory
    calories_per_100g: Decimal
    protein_per_100g: Decimal
    fat_per_100g: Decimal
    carbs_per_100g: Decimal
    serving_name: str | None
    serving_grams: Decimal | None
    household_id: int | None
    # builtin — встроенный, personal — личный, household — семейный
    source: Literal["builtin", "personal", "household"]
    # Может ли текущий пользователь изменить или удалить продукт
    can_edit: bool


class FoodListResponse(BaseModel):
    items: list[FoodResponse]
    # Сколько всего продуктов подходит под запрос (items может быть короче из-за limit)
    total: int


class FoodNutritionResponse(BaseModel):
    """Пищевая ценность заданной массы продукта."""

    food_id: int
    amount_g: Decimal
    calories: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carbs_g: Decimal


class MealFromFoodCreate(BaseModel):
    """Запись приёма пищи из справочника: вместо ручного ввода калорий.

    Пример: {"food_id": 14, "servings": 2, "eaten_at": "2026-10-27T08:30:00+03:00",
             "meal_type": "breakfast"}  → два яйца.
    Нужно указать либо amount_g (граммы), либо servings (число порций продукта).
    """

    food_id: int = Field(gt=0)
    amount_g: Decimal | None = Field(default=None, gt=0, le=10000, max_digits=8, decimal_places=2)
    servings: Decimal | None = Field(default=None, gt=0, le=100, max_digits=6, decimal_places=2)
    eaten_at: datetime
    meal_type: Literal["breakfast", "lunch", "dinner", "snack", "other"]
    notes: str | None = None

    @field_validator("eaten_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Дата и время должны содержать часовой пояс")
        return value

    @model_validator(mode="after")
    def validate_amount(self):
        if (self.amount_g is None) == (self.servings is None):
            raise ValueError("Укажите либо amount_g, либо servings")
        return self


# ---------------------------------------------------------------------------
# Шаг 66. Нормы питания и прогресс целей
# ---------------------------------------------------------------------------

ActivityLevel = Literal["sedentary", "light", "moderate", "active"]


class NutritionSettingsUpdate(BaseModel):
    """Настройки расчёта норм. Пример: {"activity_level": "light", "meals_per_day": 4}."""

    activity_level: ActivityLevel = "sedentary"
    meals_per_day: int = Field(default=4, ge=3, le=6)
    # Белок, г на кг веса; пусто — по цели автоматически
    protein_g_per_kg: Decimal | None = Field(default=None, ge=Decimal("0.8"), le=Decimal("3.5"), max_digits=3, decimal_places=1)
    # Свои калории в день вместо расчёта; пусто — считать автоматически
    calorie_override: int | None = Field(default=None, ge=800, le=6000)


class NutritionSettingsResponse(NutritionSettingsUpdate):
    model_config = ConfigDict(from_attributes=True)


class NutritionTargetResponse(BaseModel):
    """Норма питания на один день.

    ready=False означает, что для расчёта не хватает данных (список в missing),
    тогда числовые поля пустые, а в warnings сказано, что заполнить.
    """

    date: date
    ready: bool
    missing: list[str]
    warnings: list[str]

    weight_kg: Decimal | None = None
    age: int | None = None
    # Что именно использовано: male / female / average (пол не указан)
    sex_used: str | None = None

    bmr: int | None = None
    # Расход вне тренировок: BMR × коэффициент активности
    base_kcal: int | None = None
    # Расход на тренировки этого дня (оценка по MET)
    exercise_kcal: int | None = None
    tdee: int | None = None
    goal_type: str | None = None
    goal_adjustment_kcal: int | None = None

    calories: int | None = None
    protein_g: int | None = None
    fat_g: int | None = None
    carbs_g: int | None = None
    fiber_g: int | None = None
    water_ml: int | None = None

    is_training_day: bool = False
    training_minutes: int = 0
    # Пошаговое объяснение расчёта по-русски
    explanation: list[str] = []


GoalProgressStatus = Literal["no_data", "reached", "on_track", "faster", "slower", "stalled", "wrong_direction"]


class GoalProgressResponse(BaseModel):
    goal_id: int
    goal_type: str
    target_weight_kg: Decimal | None
    start_weight_kg: Decimal | None
    current_weight_kg: Decimal | None
    # Изменение с начала цели: отрицательное — вес снижается
    change_kg: Decimal | None
    remaining_kg: Decimal | None
    progress_percent: int | None
    desired_rate_kg_per_week: Decimal | None
    # Фактический темп, кг в неделю (со знаком), по последним измерениям
    actual_rate_kg_per_week: Decimal | None
    status: GoalProgressStatus
    eta_date: date | None
    target_date: date | None
    message: str



# ---------------------------------------------------------------------------
# Шаг 67. Рецепты и недельный план питания
# ---------------------------------------------------------------------------

# Типы приёмов пищи для рецептов и плана («other» здесь не нужен)
PlanMealType = Literal["breakfast", "lunch", "dinner", "snack"]
MealLocation = Literal["home", "work", "away"]
PlannedMealStatus = Literal["planned", "eaten", "skipped"]


class RecipeIngredientIn(BaseModel):
    """Ингредиент в запросе. Пример: {"food_id": 32, "amount_g": 150} — 150 г продукта №32 на порцию."""

    food_id: int = Field(gt=0)
    amount_g: Decimal = Field(gt=0, le=3000, max_digits=7, decimal_places=2)


def _check_unique_ingredients(ingredients: list[RecipeIngredientIn]) -> list[RecipeIngredientIn]:
    """Один продукт не может встречаться в рецепте дважды: сложите массы в одну строку."""
    ids = [item.food_id for item in ingredients]
    if len(ids) != len(set(ids)):
        raise ValueError("Продукт указан в рецепте несколько раз — объедините массы в одну строку")
    return ingredients


class RecipeCreate(BaseModel):
    """Новый рецепт на одну порцию.

    Пример: {"name": "Омлет с сыром", "meal_types": ["breakfast"], "portable": false,
             "prep_minutes": 10, "keeps_days": 1,
             "ingredients": [{"food_id": 17, "amount_g": 165}, {"food_id": 27, "amount_g": 20}]}
    Если указан household_id, рецепт увидят все участники семьи; иначе он личный.
    """

    name: str = Field(min_length=1, max_length=150)
    meal_types: list[PlanMealType] = Field(min_length=1, max_length=4)
    portable: bool = False
    prep_minutes: int = Field(default=15, ge=0, le=600)
    keeps_days: int = Field(default=2, ge=1, le=7)
    instructions: str | None = Field(default=None, max_length=4000)
    household_id: int | None = Field(default=None, gt=0)
    ingredients: list[RecipeIngredientIn] = Field(min_length=1, max_length=40)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Название не может быть пустым")
        return value

    @field_validator("ingredients")
    @classmethod
    def unique_ingredients(cls, value):
        return _check_unique_ingredients(value)

    @field_validator("meal_types")
    @classmethod
    def unique_meal_types(cls, value):
        return list(dict.fromkeys(value))


class RecipeUpdate(BaseModel):
    """Частичное изменение рецепта. Если передан ingredients, список заменяется целиком."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    meal_types: list[PlanMealType] | None = Field(default=None, min_length=1, max_length=4)
    portable: bool | None = None
    prep_minutes: int | None = Field(default=None, ge=0, le=600)
    keeps_days: int | None = Field(default=None, ge=1, le=7)
    instructions: str | None = Field(default=None, max_length=4000)
    ingredients: list[RecipeIngredientIn] | None = Field(default=None, min_length=1, max_length=40)

    @model_validator(mode="after")
    def reject_nulls(self):
        # Эти поля нельзя очищать: если ключ прислан, значение должно быть задано
        for field in ("name", "meal_types", "portable", "prep_minutes", "keeps_days", "ingredients"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"Поле {field} нельзя очистить")
        return self

    @field_validator("name")
    @classmethod
    def strip_name(cls, value):
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Название не может быть пустым")
        return value

    @field_validator("ingredients")
    @classmethod
    def unique_ingredients(cls, value):
        return value if value is None else _check_unique_ingredients(value)

    @field_validator("meal_types")
    @classmethod
    def unique_meal_types(cls, value):
        return value if value is None else list(dict.fromkeys(value))


class RecipeIngredientResponse(BaseModel):
    food_id: int
    name: str
    amount_g: Decimal
    # Для удобства показа: «1 яйцо» вместо граммов, если у продукта задана порция
    serving_name: str | None = None
    serving_grams: Decimal | None = None
    calories: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carbs_g: Decimal


class RecipeResponse(BaseModel):
    id: int
    name: str
    meal_types: list[PlanMealType]
    portable: bool
    prep_minutes: int
    keeps_days: int
    instructions: str | None
    household_id: int | None
    # builtin — встроенный, personal — личный, household — семейный
    source: Literal["builtin", "personal", "household"]
    can_edit: bool
    # Пищевая ценность одной порции
    calories: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carbs_g: Decimal
    ingredients: list[RecipeIngredientResponse]


class RecipeListResponse(BaseModel):
    items: list[RecipeResponse]
    total: int


class PlannedMealItemIn(BaseModel):
    """Продукт в ручном приёме пищи. Пример: {"food_id": 5, "amount_g": 200}."""

    food_id: int = Field(gt=0)
    amount_g: Decimal = Field(gt=0, le=5000, max_digits=7, decimal_places=2)


class PlannedMealCreate(BaseModel):
    """Добавление приёма пищи в план вручную.

    Вариант 1, из рецепта: {"planned_at": "2026-10-28T13:00:00+03:00", "meal_type": "lunch",
                             "location": "work", "recipe_id": 8, "portion_scale": 1.2}
    Вариант 2, из продуктов: {"planned_at": "...", "meal_type": "snack", "title": "Перекус",
                               "items": [{"food_id": 5, "amount_g": 200}]}
    """

    planned_at: datetime
    meal_type: PlanMealType
    location: MealLocation = "home"
    recipe_id: int | None = Field(default=None, gt=0)
    portion_scale: Decimal = Field(default=Decimal("1"), ge=Decimal("0.25"), le=5, max_digits=4, decimal_places=2)
    title: str | None = Field(default=None, max_length=200)
    items: list[PlannedMealItemIn] | None = Field(default=None, min_length=1, max_length=30)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("planned_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Дата и время должны содержать часовой пояс")
        return value

    @model_validator(mode="after")
    def recipe_or_items(self):
        if (self.recipe_id is None) == (self.items is None):
            raise ValueError("Укажите либо recipe_id, либо items")
        return self


class PlannedMealUpdate(BaseModel):
    """Изменение запланированного приёма пищи (пока он не съеден).

    Если меняется recipe_id или portion_scale, состав и калории пересчитываются из рецепта.
    """

    planned_at: datetime | None = None
    meal_type: PlanMealType | None = None
    location: MealLocation | None = None
    recipe_id: int | None = Field(default=None, gt=0)
    portion_scale: Decimal | None = Field(default=None, ge=Decimal("0.25"), le=5, max_digits=4, decimal_places=2)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("planned_at")
    @classmethod
    def require_timezone(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Дата и время должны содержать часовой пояс")
        return value

    @model_validator(mode="after")
    def reject_nulls(self):
        for field in ("planned_at", "meal_type", "location", "portion_scale", "recipe_id"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"Поле {field} нельзя очистить")
        return self


class PlannedMealItemResponse(BaseModel):
    food_id: int | None
    name: str
    amount_g: Decimal
    calories: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carbs_g: Decimal


class PlannedMealResponse(BaseModel):
    id: int
    plan_date: date
    planned_at: datetime
    meal_type: PlanMealType
    location: MealLocation
    status: PlannedMealStatus
    recipe_id: int | None
    title: str
    portion_scale: Decimal
    calories: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carbs_g: Decimal
    notes: str | None
    meal_entry_id: int | None
    items: list[PlannedMealItemResponse]


class EatPlannedMealRequest(BaseModel):
    """Отметка «съел». Пример: {"eaten_at": "2026-10-28T13:10:00+03:00"}; без тела — текущий момент."""

    eaten_at: datetime | None = None

    @field_validator("eaten_at")
    @classmethod
    def require_timezone(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Дата и время должны содержать часовой пояс")
        return value


class MealPlanGenerateRequest(BaseModel):
    """Автоматическое составление плана.

    Пример: {"start": "2026-10-26", "days": 7, "overwrite": false, "batch_days": 2}
    batch_days — сколько дней подряд можно повторять один и тот же обед или ужин
    (готовка «про запас»): 1 — каждый день разное, 2–3 — меньше готовки.
    overwrite=false не трогает дни, где уже есть приёмы пищи.
    """

    start: date
    days: int = Field(default=7, ge=1, le=14)
    overwrite: bool = False
    batch_days: int = Field(default=2, ge=1, le=3)


class DayTargetBrief(BaseModel):
    """Краткая норма дня для плана (подробности — в разделе «Нормы и цели»)."""

    ready: bool
    calories: int | None = None
    protein_g: int | None = None
    fat_g: int | None = None
    carbs_g: int | None = None
    is_training_day: bool = False
    training_minutes: int = 0


class MealPlanDay(BaseModel):
    date: date
    target: DayTargetBrief
    # Суммы по приёмам пищи, не пропущенным пользователем
    planned_calories: Decimal
    planned_protein_g: Decimal
    planned_fat_g: Decimal
    planned_carbs_g: Decimal
    meals: list[PlannedMealResponse]
    warnings: list[str]


class MealPlanWeekResponse(BaseModel):
    start: date
    end: date
    timezone: str
    # Нормы нельзя рассчитать (нет веса или даты рождения): автосоставление недоступно
    target_ready: bool
    warnings: list[str]
    days: list[MealPlanDay]


class MealPlanGenerateResponse(BaseModel):
    created_meals: int
    # Сколько ещё не съеденных приёмов пищи заменено (при overwrite=true)
    replaced_meals: int
    # Дни, которые не тронули, потому что в них уже есть план
    skipped_days: list[date]
    warnings: list[str]


# ---------------------------------------------------------------------------
# Шаг 68. Список закупок и план готовки
# ---------------------------------------------------------------------------


class ShoppingItemResponse(BaseModel):
    # "food:12" для продукта справочника или "name:хлеб" для продукта, удалённого из справочника
    key: str
    food_id: int | None
    name: str
    category: str
    # Сколько нужно купить (граммы, округлено вверх до целого)
    amount_g: Decimal
    # Для продуктов с порцией: сколько порций это составляет, например 11 яиц
    serving_name: str | None = None
    serving_grams: Decimal | None = None
    servings: Decimal | None = None
    # В каких блюдах понадобится (не больше пяти названий)
    used_in: list[str]
    checked: bool
    # Только в семейном списке: кто из участников это ест, например ["Даня", "Леся"]
    members: list[str] = Field(default_factory=list)
    # Только в семейном списке: кто отметил «куплено» (имя участника)
    checked_by: str | None = None


class ShoppingListResponse(BaseModel):
    start: date
    end: date
    items: list[ShoppingItemResponse]
    checked_count: int
    # Сколько приёмов пищи учтено (только «в плане»: съеденные и пропущенные не покупаются)
    meals_count: int
    # Только в семейном списке: чьи планы учтены, например ["Даня", "Леся"]
    members: list[str] = Field(default_factory=list)


class ShoppingCheckRequest(BaseModel):
    """Отметка «куплено». Пример: {"start": "2026-10-26", "key": "food:12", "checked": true}."""

    start: date
    key: str = Field(min_length=1, max_length=100)
    checked: bool


class CookingMealRef(BaseModel):
    id: int
    plan_date: date
    meal_type: PlanMealType
    planned_at: datetime
    location: MealLocation
    portion_scale: Decimal
    # Только в семейном плане готовки: для кого эта порция
    user_id: int | None = None
    user_name: str | None = None


class CookingIngredient(BaseModel):
    name: str
    amount_g: Decimal


class CookingSessionResponse(BaseModel):
    recipe_id: int
    recipe_name: str
    # Когда готовить: накануне вечером (evening_before) или в день первого приёма (same_day)
    cook_date: date
    cook_when: Literal["evening_before", "same_day"]
    # Сколько порций сварить (сумма размеров порций по приёмам пищи)
    portions: Decimal
    # Ориентировочное время: время рецепта + 5 минут на каждую следующую порцию
    estimated_minutes: int
    keeps_days: int
    instructions: str | None
    meals: list[CookingMealRef]
    ingredients: list[CookingIngredient]


class CookingPlanResponse(BaseModel):
    start: date
    end: date
    sessions: list[CookingSessionResponse]
    total_minutes: int


# ---------------------------------------------------------------------------
# Шаг 69. Семейное планирование
# ---------------------------------------------------------------------------


class FamilyPlanningMember(BaseModel):
    """Участник семьи и его выбор «планировать питание вместе».

    Пример: {"user_id": 2, "name": "Леся", "role": "member", "plans_together": true, "is_me": false}
    """

    user_id: int
    name: str
    role: str
    plans_together: bool
    is_me: bool


class FamilyPlanningState(BaseModel):
    household_id: int
    members: list[FamilyPlanningMember]
    # Сколько участников включили «Планировать вместе» (общий план возможен от двух)
    together_count: int


class FamilyPlanningUpdate(BaseModel):
    """Включить или выключить своё участие в общем плане. Пример: {"plans_together": true}."""

    plans_together: bool


class FamilyPlannedMeal(BaseModel):
    """Приём пищи участника в семейном виде.

    Калории и БЖУ других участников не показываются — только что, когда и в каком размере порции.
    """

    id: int
    planned_at: datetime
    meal_type: PlanMealType
    location: MealLocation
    status: PlannedMealStatus
    title: str
    recipe_id: int | None
    portion_scale: Decimal
    # True, если у другого участника в то же время то же блюдо (едят вместе)
    shared: bool


class FamilyPlanMemberDay(BaseModel):
    user_id: int
    name: str
    meals: list[FamilyPlannedMeal]


class FamilyPlanDay(BaseModel):
    date: date
    members: list[FamilyPlanMemberDay]


class FamilyPlanWeekResponse(BaseModel):
    household_id: int
    start: date
    end: date
    # Только те, кто включил «Планировать вместе»
    members: list[FamilyPlanningMember]
    days: list[FamilyPlanDay]


class FamilyPlanGenerateRequest(MealPlanGenerateRequest):
    """Составление общего плана.

    Пример: {"start": "2026-10-26", "days": 7, "overwrite": false, "batch_days": 2,
             "shared_meal_types": ["dinner"]}
    shared_meal_types — какие приёмы пищи семья ест вместе (одно блюдо на всех, порции разные).
    Пустой список — каждому свои блюда, но с общими закупками.
    """

    shared_meal_types: list[PlanMealType] = Field(default_factory=lambda: ["dinner"], max_length=4)

    @field_validator("shared_meal_types")
    @classmethod
    def drop_duplicates(cls, value):
        # ["dinner", "dinner"] → ["dinner"]; порядок сохраняется
        return list(dict.fromkeys(value))


class FamilyPlanMemberResult(BaseModel):
    user_id: int
    name: str
    created_meals: int
    replaced_meals: int
    skipped_days: list[date]


class FamilyPlanGenerateResponse(BaseModel):
    members: list[FamilyPlanMemberResult]
    # Сколько общих приёмов пищи составлено (один общий ужин для двоих считается за один)
    shared_meals: int
    warnings: list[str]


# ---------------------------------------------------------------------------
# Шаг 70. Фото прогресса
# ---------------------------------------------------------------------------

PhotoAngle = Literal["front", "side", "back", "other"]


class ProgressPhotoResponse(BaseModel):
    """Данные о фото. Сам файл отдаёт GET {url}.

    Пример: {"id": 3, "taken_on": "2026-10-27", "angle": "front", "note": "Утром, натощак",
             "content_type": "image/jpeg", "size_bytes": 412345, "created_at": "...",
             "url": "/users/1/progress-photos/3/file"}
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    taken_on: date
    angle: PhotoAngle
    note: str | None
    content_type: str
    size_bytes: int
    created_at: datetime
    url: str


class ProgressPhotoUpdate(BaseModel):
    """Изменение данных фото. Пример: {"taken_on": "2026-10-20", "angle": "side", "note": null}.

    Поля, которых нет в теле, не меняются; "note": null очищает подпись.
    """

    taken_on: date | None = None
    angle: PhotoAngle | None = None
    note: str | None = Field(default=None, max_length=300)

    @field_validator("note")
    @classmethod
    def clean_note(cls, value):
        # "  " → None; лишние пробелы по краям убираем
        return (value.strip() or None) if value is not None else None


# ---------------------------------------------------------------------------
# Шаг 72. Безопасность: смена пароля
# ---------------------------------------------------------------------------


class ChangePasswordRequest(BaseModel):
    """Смена пароля. Пример: {"current_password": "старый-пароль-123", "new_password": "новый-длинный-пароль-456"}."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)



# ---------------------------------------------------------------------------
# Релиз 1.1. Повторяющиеся доходы и платежи, бюджетные циклы, нагрузка, цели, удаление аккаунта
# ---------------------------------------------------------------------------

# Как часто повторяется операция
RuleFrequency = Literal["weekly", "biweekly", "semimonthly", "monthly", "yearly"]

# Бюджетный период: календарный месяц или «от дохода до дохода»
CycleMode = Literal["calendar", "income"]

# Вид финансовой цели: накопление, простой долг, кредит с процентами
GoalKind = Literal["savings", "debt", "loan"]

# Состояние повторения: ожидается / оплачено (получено) / пропущено
OccurrenceStatus = Literal["pending", "posted", "skipped"]

# Насколько серьёзно сообщение-совет
Severity = Literal["info", "warning", "danger"]


def _clean_name(value: str) -> str:
    """Убирает пробелы по краям; название из одних пробелов не допускается."""
    value = value.strip()
    if not value:
        raise ValueError("Название не может быть пустым")
    return value


def check_rule_schedule(
    kind: str,
    frequency: str,
    day_of_month: int | None,
    second_day_of_month: int | None,
    end_on: date | None,
    start_on: date,
    auto_post: bool | None,
) -> None:
    """Общие правила для нового и изменённого правила; при нарушении бросает ValueError.

    Пример ошибки: доход с end_on → «У дохода нет даты окончания…».
    """
    if frequency == "semimonthly":
        if day_of_month is None or second_day_of_month is None:
            raise ValueError("Для «два раза в месяц» укажите оба дня месяца")
        if day_of_month == second_day_of_month:
            raise ValueError("Дни месяца для «два раза в месяц» должны различаться")
    elif second_day_of_month is not None:
        raise ValueError("Второй день месяца указывается только для «два раза в месяц»")
    if frequency not in ("monthly", "semimonthly") and day_of_month is not None:
        raise ValueError("day_of_month указывается только для ежемесячных правил")

    if kind == "income":
        if auto_post:
            raise ValueError("Доход не начисляется автоматически: его подтверждают, когда деньги поступили")
        if end_on is not None:
            raise ValueError(
                "У дохода нет даты окончания: бюджетный период заканчивается датой следующего основного дохода. "
                "Чтобы доход больше не ожидался, поставьте его на паузу или удалите"
            )

    if end_on is not None and end_on < start_on:
        raise ValueError("Дата окончания не может быть раньше даты начала")


class RecurringRuleCreate(BaseModel):
    """Новое повторяющееся правило: доход или обязательный платёж.

    Примеры тела запроса:
        Зарплата 10-го и 25-го числа (основной доход, подтверждается «Получено»):
        {"kind": "income", "name": "Зарплата", "amount": 50000, "frequency": "semimonthly",
         "start_on": "2026-10-10", "day_of_month": 10, "second_day_of_month": 25}
        Аренда 3-го числа (нужно подтверждать «Оплачено»):
        {"kind": "expense", "name": "Аренда", "amount": 35000, "frequency": "monthly",
         "start_on": "2026-11-03", "day_of_month": 3}
    """

    kind: FinanceKind
    name: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)

    # Если не указана, берётся категория по умолчанию: «Зарплата» для дохода,
    # «Обязательные платежи» для расхода (создаётся при первом использовании)
    category_id: int | None = Field(default=None, gt=0)

    frequency: RuleFrequency
    start_on: date

    # Для monthly и первый день для semimonthly; если не указан, берётся день из start_on
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    # Только для semimonthly: второй день месяца, например 25
    second_day_of_month: int | None = Field(default=None, ge=1, le=31)
    # Только для платежей (последний платёж по кредиту); у доходов не бывает
    end_on: date | None = None

    # Только для платежей: списывать ли самостоятельно (по умолчанию нет). Доход всегда подтверждается
    auto_post: bool | None = None

    # Основной (по умолчанию) или дополнительный. Границы бюджетного периода задают основные доходы
    is_primary: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return _clean_name(value)

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.frequency in ("monthly", "semimonthly") and self.day_of_month is None:
            self.day_of_month = self.start_on.day
        check_rule_schedule(
            self.kind, self.frequency, self.day_of_month, self.second_day_of_month,
            self.end_on, self.start_on, self.auto_post,
        )
        return self


class RecurringRuleUpdate(BaseModel):
    """Частичное изменение правила: передаются только меняемые поля.

    Пример: {"amount": 36000} или {"is_active": false} (поставить на паузу).
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    category_id: int | None = Field(default=None, gt=0)
    frequency: RuleFrequency | None = None
    start_on: date | None = None
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    second_day_of_month: int | None = Field(default=None, ge=1, le=31)
    end_on: date | None = None
    auto_post: bool | None = None
    is_primary: bool | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)

    @model_validator(mode="after")
    def validate_update(self):
        # Эти поля нельзя «обнулить» значением null (end_on и day_of_month можно)
        for field in ("name", "amount", "frequency", "start_on", "auto_post", "is_primary", "is_active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"Поле {field} нельзя очистить")
        return self


class RecurringRuleResponse(BaseModel):
    """Правило и ближайшая дата его срабатывания."""

    id: int
    ledger_id: int
    kind: FinanceKind
    category_id: int
    category_name: str
    name: str
    amount: Decimal
    frequency: RuleFrequency
    start_on: date
    day_of_month: int | None
    second_day_of_month: int | None
    end_on: date | None
    auto_post: bool
    # Основной (задаёт границы бюджетного периода, если это доход) или дополнительный
    is_primary: bool
    is_active: bool
    # Сколько правило приносит (или стоит) за месяц; None для «раз в две недели»:
    # в месяце бывает две или три выплаты, а среднее не совпадает с реальностью
    monthly_amount: Decimal | None
    # Ближайшая будущая или сегодняшняя необработанная дата; None, если правило закончилось
    next_due_on: date | None
    created_by_user_id: int | None
    # Может ли текущий пользователь менять и удалять правило
    can_edit: bool


class OccurrenceConfirm(BaseModel):
    """Подтверждение выплаты. Оба поля необязательны.

    Пример: {"amount": 34800, "occurred_on": "2026-11-03"} (фактическая сумма отличалась от плановой).
    """

    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    occurred_on: date | None = None


class OccurrenceResponse(BaseModel):
    """Одно повторение правила: что, когда, сколько и в каком состоянии."""

    rule_id: int
    rule_name: str
    kind: FinanceKind
    category_name: str
    due_on: date
    # Плановая сумма из правила
    planned_amount: Decimal
    # Фактическая сумма, если выплата отмечена, иначе плановая
    amount: Decimal
    status: OccurrenceStatus
    # True, если дата прошла, а выплата не отмечена
    overdue: bool
    transaction_id: int | None
    # Основной или дополнительный доход / платёж
    is_primary: bool = True


class IncomePromptResponse(BaseModel):
    """Ожидаемое поступление, о котором пора спросить «Поступил ли платёж?».

    Спрашиваем с двух дней до плановой даты до двух дней после неё. Пример:
    {"ledger_id": 1, "ledger_kind": "personal", "household_name": null, "currency": "RUB",
     "rule_id": 3, "rule_name": "Зарплата", "due_on": "2026-10-25", "planned_amount": "90000", "is_primary": true}
    """

    ledger_id: int
    ledger_kind: LedgerKind
    household_name: str | None
    currency: str
    rule_id: int
    rule_name: str
    due_on: date
    planned_amount: Decimal
    is_primary: bool


class FinanceHomeLedger(BaseModel):
    """Деньги одной книги для главной страницы: сколько всего и сколько свободно в текущем периоде.

    total — баланс, «кошелёк»: только фактические операции по сегодняшний день включительно
            (подтверждённые доходы, расходы, автосписания) плюс корректировки баланса.
            Ожидаемые доходы и ещё не оплаченные платежи сюда не входят.
    free — баланс минус неоплаченные обязательные платежи до следующего основного дохода (spending_plan);
           ожидаемые доходы не учитываются, пока их не подтвердят.
    """

    ledger_id: int
    kind: LedgerKind
    household_id: int | None
    household_name: str | None
    currency: str
    total: Decimal
    # Баланс минус обязательные платежи до следующего основного дохода; None — следующего дохода нет
    free: Decimal | None
    # Дата следующего основного дохода: «Свободно до 10 ноя»
    free_until: date | None
    spending_status: Literal["ok", "gap", "no_income", "income_today"]
    # Текст вместо числа для особых случаев (см. SpendingPlanResponse.note)
    spending_note: str | None
    period_start: date
    period_end: date


class BalanceSet(BaseModel):
    """«Сколько сейчас на самом деле»: фактический остаток книги. Пример: {"actual": 52300, "note": "сверка с банком"}.

    Сервер сам считает разницу с текущим «Всего» и сохраняет её как корректировку.
    Остаток может быть отрицательным (например, ушли в минус по кредитке).
    """

    actual: Decimal = Field(ge=-9_999_999_999, le=9_999_999_999, max_digits=12, decimal_places=2)
    note: str | None = Field(default=None, max_length=250)

    @field_validator("note")
    @classmethod
    def strip_note(cls, value: str | None) -> str | None:
        # Пустое пояснение храним как отсутствующее
        value = value.strip() if value else None
        return value or None


class BalanceAdjustmentResponse(BaseModel):
    """Одна корректировка. Пример: {"id": 4, "amount": "2300.00", "adjusted_on": "2026-10-29",
    "note": "сверка с банком", "created_by_user_id": 1, "created_by_name": "Даня", "created_at": "..."}."""

    id: int
    # Разница со знаком: плюс — денег оказалось больше насчитанного, минус — меньше
    amount: Decimal
    adjusted_on: date
    note: str | None
    created_by_user_id: int | None
    created_by_name: str | None
    created_at: datetime


class LedgerBalanceResponse(BaseModel):
    """Баланс книги и последние корректировки (новые сначала).

    Пример: {"ledger_id": 1, "currency": "RUB", "total": "52300.00", "adjustments_total": "2300.00",
             "adjustments": [{"id": 4, "amount": "2300.00", ...}]}
    """

    ledger_id: int
    currency: str
    total: Decimal
    # Сумма всех корректировок: на сколько «Всего» отличается от простой суммы операций
    adjustments_total: Decimal
    adjustments: list[BalanceAdjustmentResponse]


class LedgerCycleUpdate(BaseModel):
    """Смена режима бюджетного периода. Пример: {"cycle_mode": "income"}."""

    cycle_mode: CycleMode


class AdviceItem(BaseModel):
    """Совет или предупреждение для человека, уже написанное словами."""

    code: str
    severity: Severity
    text: str


class CycleResponse(BaseModel):
    """Один бюджетный период: сколько придёт, сколько обязательных платежей и что останется."""

    start: date
    end: date
    is_current: bool
    days_total: int
    # Сколько дней осталось в текущем периоде, включая сегодня; для остальных None
    days_left: int | None
    income_received: Decimal
    income_expected: Decimal
    income_total: Decimal
    mandatory_paid: Decimal
    mandatory_pending: Decimal
    mandatory_total: Decimal
    other_spent: Decimal
    # Доход минус обязательные платежи (до обычных трат)
    free_after_mandatory: Decimal
    # Прогноз периода: доход (вместе с ожидаемым) минус обязательные платежи минус обычные траты.
    # Для «сколько можно тратить сейчас» используется не он, а SpendingPlanResponse (только реальные деньги)
    available: Decimal
    # Доля обязательных платежей в доходе (1.0 = 100 %); None, если дохода нет
    mandatory_share: float | None
    # ok — запас есть, tight — обязательные платежи занимают больше 70 % дохода, gap — не хватает денег
    status: Literal["ok", "tight", "gap"]
    items: list[OccurrenceResponse]


class SpendingPlanResponse(BaseModel):
    """«Баланс → Свободно → Можно тратить в день»: один расчёт для главной и «Финансы → Обзор».

    balance — реальные деньги (подтверждённые операции по сегодня и корректировки);
    mandatory_due — неоплаченные обязательные платежи от сегодня до дня перед следующим основным доходом;
    free = balance − mandatory_due (None, если следующего основного дохода нет);
    days_left — дни до следующего основного дохода (сегодня считается, день дохода нет);
    daily_allowance = free ÷ days_left; None, если дней 0, дохода нет или денег не хватает;
    status: ok | gap (не хватает) | no_income (нет следующего дохода) | income_today (доход сегодня);
    note — текст вместо числа для особых случаев, например «Не хватает 5 000 ₽ до 10 ноя».
    Пример: {"balance": "86000.00", "mandatory_due": "35000.00", "free": "51000.00",
             "next_income_on": "2026-11-10", "days_left": 13, "daily_allowance": "3923.08", "status": "ok", "note": null}
    """

    balance: Decimal
    mandatory_due: Decimal
    free: Decimal | None
    next_income_on: date | None
    days_left: int | None
    daily_allowance: Decimal | None
    status: Literal["ok", "gap", "no_income", "income_today"]
    note: str | None


class CyclesResponse(BaseModel):
    ledger_id: int
    currency: str
    mode: CycleMode
    today: date
    # Что можно тратить сейчас (общий расчёт, как на главной)
    spending: SpendingPlanResponse
    cycles: list[CycleResponse]
    advice: list[AdviceItem]


class PeriodSummaryResponse(BaseModel):
    """Итоги за произвольный период (месяц или бюджетный цикл)."""

    ledger_id: int
    start: date
    end: date
    currency: str
    income: Decimal
    expense: Decimal
    balance: Decimal
    categories: list[CategorySummary]


class LoadItem(BaseModel):
    name: str
    monthly_amount: Decimal


class LoadResponse(BaseModel):
    """Оценка финансовой нагрузки: хватает ли дохода на обязательные платежи.

    Все суммы приведены к среднему месяцу. Пример для зарплаты 140 000 ₽ и обязательных платежей 100 000 ₽:
    income_monthly=140000, mandatory_monthly=100000, free_monthly=40000, mandatory_share=71.4, status="critical".
    """

    ledger_id: int
    currency: str
    income_monthly: Decimal
    mandatory_monthly: Decimal
    free_monthly: Decimal
    # Обязательные платежи в процентах от дохода (71.4 = 71,4 %); None, если дохода нет
    mandatory_share: float | None
    status: Literal["no_income", "comfortable", "moderate", "high", "critical"]
    # Средние обычные траты за последние месяцы (если по ним есть данные)
    avg_other_expense_monthly: Decimal | None
    # Что остаётся после обязательных платежей и обычных трат; None, если трат ещё нет
    left_after_expenses: Decimal | None
    # Сколько ещё можно взять в ежемесячный платёж, не выходя за 50 % дохода (не меньше 0)
    safe_extra_payment: Decimal
    # Подушка безопасности: три месяца обязательных платежей
    emergency_fund_target: Decimal
    mandatory_items: list[LoadItem]
    advice: list[AdviceItem]


class LoadSimulationResponse(BaseModel):
    """Что будет, если взять ещё один ежемесячный платёж (кредит, рассрочку)."""

    ledger_id: int
    currency: str
    payment: Decimal
    income_monthly: Decimal
    mandatory_monthly: Decimal
    new_mandatory_monthly: Decimal
    new_free_monthly: Decimal
    new_mandatory_share: float | None
    verdict: Literal["ok", "risky", "not_recommended"]
    text: str
    advice: list[AdviceItem]


class FinanceGoalCreate(BaseModel):
    """Новая финансовая цель.

    Примеры тела запроса:
        Накопление: {"kind": "savings", "name": "Отпуск", "target_amount": 200000, "start_amount": 15000}
        Долг другу: {"kind": "debt", "name": "Долг Ивану", "target_amount": 30000, "start_amount": 5000}
        Кредит:     {"kind": "loan", "name": "Кредит в банке", "target_amount": 100000,
                     "interest_rate": 60, "payment_day": 15}
    Личная или совместная цель определяется книгой в адресе запроса (личная или семейная).
    """

    kind: GoalKind
    name: str = Field(min_length=1, max_length=100)
    # Накопление: цель. Долг: исходная сумма. Кредит: текущий основной долг
    target_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    # Накопление: уже накоплено. Долг: уже выплачено. Для кредита всегда 0
    start_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    # Только для кредита: годовая ставка в процентах и день ежемесячного платежа
    interest_rate: Decimal | None = Field(default=None, ge=0, le=1000, max_digits=6, decimal_places=3)
    payment_day: int | None = Field(default=None, ge=1, le=31)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return _clean_name(value)

    @model_validator(mode="after")
    def validate_kind_fields(self):
        if self.kind == "loan":
            if self.interest_rate is None or self.payment_day is None:
                raise ValueError("Для кредита нужны годовая ставка и день ежемесячного платежа")
            if self.start_amount != 0:
                raise ValueError("Для кредита укажите текущий основной долг, а не выплаченную часть")
        else:
            if self.interest_rate is not None or self.payment_day is not None:
                raise ValueError("Ставка и день платежа указываются только для кредита")
            if self.kind == "debt" and self.start_amount > self.target_amount:
                raise ValueError("Выплачено не может быть больше суммы долга")
        return self


class FinanceGoalUpdate(BaseModel):
    """Частичное изменение цели. Пример: {"name": "Отпуск в Грузии", "target_amount": 250000}."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    target_amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    start_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    interest_rate: Decimal | None = Field(default=None, ge=0, le=1000, max_digits=6, decimal_places=3)
    payment_day: int | None = Field(default=None, ge=1, le=31)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)

    @model_validator(mode="after")
    def validate_update(self):
        for field in ("name", "target_amount", "start_amount"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"Поле {field} нельзя очистить")
        return self


class FinanceGoalEntryCreate(BaseModel):
    """Взнос или платёж. Пример: {"amount": 20000, "paid_on": "2026-10-15", "note": "Платёж за октябрь"}."""

    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    # Если не указана, берётся сегодняшняя дата пользователя
    paid_on: date | None = None
    note: str | None = Field(default=None, max_length=250)


class FinanceGoalEntryResponse(BaseModel):
    id: int
    goal_id: int
    user_id: int | None
    user_name: str
    paid_on: date
    amount: Decimal
    # Только для кредита: сколько платежа ушло банку и сколько уменьшило основной долг
    interest_part: Decimal | None
    principal_part: Decimal | None
    balance_after: Decimal | None
    note: str | None
    # Расход, из которого создана запись; None — взнос внесён вручную. Такую запись меняют через расход
    transaction_id: int | None = None
    can_delete: bool


class FinanceGoalContributor(BaseModel):
    """Вклад одного участника в цель. Из долей складывается разноцветный прогресс-бар."""

    user_id: int | None
    name: str
    total: Decimal
    # Доля от общей суммы взносов, от 0 до 1
    share: float


class FinanceGoalResponse(BaseModel):
    """Цель и её текущее состояние.

    remaining: накопление — сколько осталось накопить; долг и кредит — остаток основного долга.
    paid_total: накопление — сколько накоплено; долг — сколько выплачено; кредит — сколько внесено платежами.
    """

    id: int
    ledger_id: int
    shared: bool
    kind: GoalKind
    name: str
    target_amount: Decimal
    start_amount: Decimal
    interest_rate: Decimal | None
    payment_day: int | None
    next_payment_on: date | None
    currency: str
    progress: float
    remaining: Decimal
    paid_total: Decimal
    done: bool
    # Кредит: сколько из последнего платежа ушло банку на проценты, и сколько процентов выплачено всего
    last_interest: Decimal | None
    interest_paid_total: Decimal | None
    contributors: list[FinanceGoalContributor]
    can_edit: bool
    created_by_user_id: int | None
    created_at: datetime


class FinanceGoalDetailResponse(FinanceGoalResponse):
    """Цель вместе с историей взносов (новые сверху)."""

    entries: list[FinanceGoalEntryResponse]


class DeleteAccountRequest(BaseModel):
    """Удаление аккаунта. Пароль нужен, чтобы удалить мог только владелец, а не любой, у кого оказался токен."""

    password: str = Field(min_length=1, max_length=128)


class HouseholdBrief(BaseModel):
    id: int
    name: str


class HouseholdLeaveInfo(BaseModel):
    id: int
    name: str
    # Кому перейдёт владение, если удаляется владелец семьи; иначе None
    new_owner_name: str | None


class DeletionPreviewResponse(BaseModel):
    """Что произойдёт при удалении аккаунта."""

    email: str | None
    households_to_delete: list[HouseholdBrief]
    households_to_leave: list[HouseholdLeaveInfo]
    counts: dict[str, int]
