from sqlalchemy import (Date, CheckConstraint, DateTime,
                        ForeignKey, Integer, String, func,
                        text, Index, Numeric, Text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime, date
from decimal import Decimal



class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint(
            "sex IN ('male', 'female', 'unspecified')",
            name="ck_users_sex",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Временное поле для совместимости со старыми записями.
    age: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    birth_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    sex: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    height_cm: Mapped[int] = mapped_column(Integer)

    occupation: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'UTC'"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Household(Base):
    __tablename__ = "households"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

class HouseholdMember(Base):
    __tablename__ = "household_members"

    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'admin', 'member')",
            name="ck_household_members_role",
        ),
    )

    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id"),
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        primary_key=True,
    )

    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'member'"),
    )

    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        )


class WeightRecord(Base):
    __tablename__ = "weight_records"

    __table_args__ = (
        CheckConstraint(
            "weight_kg > 0",
            name="ck_weight_records_weight_positive",
        ),
        CheckConstraint(
            """
            body_fat_percent IS NULL
            OR (
                body_fat_percent >= 0
                AND body_fat_percent <= 100
            )
            """,
            name="ck_weight_records_body_fat_range",
        ),
        Index(
            "ix_weight_records_user_date",
            "user_id",
            "measurement_date",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    measurement_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    weight_kg: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )

    body_fat_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )