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