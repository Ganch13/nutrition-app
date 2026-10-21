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

    # Email для входа; у старых пользователей пока может отсутствовать
    email: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
    )

    # Хеш пароля для авторизации; у старых пользователей пока может отсутствовать
    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
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




class Goal(Base):
    __tablename__ = "goals"

    __table_args__ = (
        # Допустимые типы целей
        CheckConstraint(
            """
            goal_type IN (
                'fat_loss',
                'muscle_gain',
                'weight_maintenance',
                'performance',
                'general_health'
            )
            """,
            name="ck_goals_goal_type",
        ),

        # Приоритет: от 1 (самый высокий) до 5
        CheckConstraint(
            "priority BETWEEN 1 AND 5",
            name="ck_goals_priority",
        ),

        # Целевой вес должен быть положительным, если указан
        CheckConstraint(
            "target_weight_kg IS NULL OR target_weight_kg > 0",
            name="ck_goals_target_weight_positive",
        ),

        # Процент жира: от 0 до 100
        CheckConstraint(
            """
            target_body_fat_percent IS NULL
            OR (
                target_body_fat_percent >= 0
                AND target_body_fat_percent <= 100
            )
            """,
            name="ck_goals_body_fat_range",
        ),

        # Желаемое изменение веса: более 0, не более 5 кг в неделю
        CheckConstraint(
            """
            desired_rate_kg_per_week IS NULL
            OR (
                desired_rate_kg_per_week > 0
                AND desired_rate_kg_per_week <= 5
            )
            """,
            name="ck_goals_desired_rate_range",
        ),

        # Дата завершения не может быть раньше даты начала
        CheckConstraint(
            "target_date IS NULL OR target_date >= start_date",
            name="ck_goals_target_date",
        ),

        # Допустимые статусы цели
        CheckConstraint(
            "status IN ('active', 'completed', 'paused', 'cancelled')",
            name="ck_goals_status",
        ),

        # Ускоряем поиск целей конкретного пользователя по статусу
        Index("ix_goals_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    # Тип цели: снижение веса, набор мышц, поддержание веса и т. д.
    goal_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    # Приоритет от 1 до 5
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("3"),
    )

    # Желаемый вес в килограммах
    target_weight_kg: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )

    # Желаемый процент жира
    target_body_fat_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )

    # Желаемая скорость изменения веса, кг в неделю
    desired_rate_kg_per_week: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 2),
        nullable=True,
    )

    # Дата начала цели; по умолчанию текущая дата PostgreSQL
    start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        server_default=func.current_date(),
    )

    # Желаемая дата достижения цели
    target_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    # Статус: active, completed, paused или cancelled
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'active'"),
    )

    # Дополнительные сведения о цели
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Дата и время создания записи
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ScheduleEvent(Base):
    __tablename__ = "schedule_events"

    __table_args__ = (
        # Допустимые типы событий
        CheckConstraint(
            """
            event_type IN (
                'sleep',
                'work',
                'meal',
                'workout',
                'personal',
                'other'
            )
            """,
            name="ck_schedule_events_type",
        ),

        # Окончание события должно быть позже начала
        CheckConstraint(
            "end_at > start_at",
            name="ck_schedule_events_time_range",
        ),

        # Ускоряем получение расписания пользователя по времени
        Index(
            "ix_schedule_events_user_start",
            "user_id",
            "start_at",
        ),
    )

    # Уникальный идентификатор события
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    # Пользователь, которому принадлежит событие
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    # Тип события: сон, работа, приём пищи и т. д.
    event_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # Название события
    title: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    # Момент начала с учётом часового пояса
    start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Момент окончания с учётом часового пояса
    end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Место проведения, если оно указано
    location: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    # Дополнительная информация
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Дата и время создания записи
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    __table_args__ = (
        # Допустимые статусы тренировочной сессии
        CheckConstraint(
            "status IN ('planned', 'completed', 'skipped', 'cancelled')",
            name="ck_training_sessions_status",
        ),

        # Окончание занятия должно быть позже его начала
        CheckConstraint(
            "end_at > start_at",
            name="ck_training_sessions_time_range",
        ),

        # Ускоряем поиск тренировок пользователя по времени
        Index(
            "ix_training_sessions_user_start",
            "user_id",
            "start_at",
        ),
    )

    # Уникальный идентификатор тренировочной сессии
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    # Пользователь, которому принадлежит тренировка
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    # Связанное событие расписания, если оно существует
    # Одна запись расписания может быть связана с одной сессией
    schedule_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("schedule_events.id"),
        nullable=True,
        unique=True,
    )

    # Название занятия
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    # Время начала тренировочной сессии
    start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Время окончания тренировочной сессии
    end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Статус: запланирована, выполнена, пропущена или отменена
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'planned'"),
    )

    # Дополнительная информация
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Дата и время создания записи
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Workout(Base):
    __tablename__ = "workouts"

    __table_args__ = (
        # Допустимые типы нагрузки
        CheckConstraint(
            "load_type IN ('strength', 'cardio', 'mixed', 'other')",
            name="ck_workouts_load_type",
        ),

        # Допустимая планируемая интенсивность
        CheckConstraint(
            "planned_intensity IN ('low', 'moderate', 'high')",
            name="ck_workouts_planned_intensity",
        ),

        # Фактическая интенсивность может быть неизвестна
        CheckConstraint(
            """
            actual_intensity IS NULL
            OR actual_intensity IN ('low', 'moderate', 'high')
            """,
            name="ck_workouts_actual_intensity",
        ),

        # Окончание тренировки должно быть позже начала
        CheckConstraint(
            "end_at > start_at",
            name="ck_workouts_time_range",
        ),

        # Ускоряем получение тренировок внутри сессии
        Index(
            "ix_workouts_session_start",
            "training_session_id",
            "start_at",
        ),
    )

    # Уникальный идентификатор отдельной тренировки
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    # Сессия, к которой относится эта тренировка
    training_session_id: Mapped[int] = mapped_column(
        ForeignKey("training_sessions.id"),
        nullable=False,
    )

    # Название: силовая тренировка, баскетбол и т. д.
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    # Тип нагрузки: strength, cardio, mixed или other
    load_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # Планируемая интенсивность: low, moderate или high
    planned_intensity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # Фактическая интенсивность после выполнения
    actual_intensity: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    # Время начала отдельной тренировки
    start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Время окончания отдельной тренировки
    end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Дополнительные сведения
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Дата и время создания записи
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class MealEntry(Base):
    # Таблица записей о приёмах пищи
    __tablename__ = "meal_entries"

    __table_args__ = (
        # Допустимые типы приёмов пищи
        CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snack', 'other')",
            name="ck_meal_entries_meal_type",
        ),

        # Калорийность не может быть отрицательной
        CheckConstraint(
            "calories >= 0",
            name="ck_meal_entries_calories",
        ),

        # Белки, жиры и углеводы не могут быть отрицательными
        CheckConstraint(
            "protein_g >= 0 AND fat_g >= 0 AND carbs_g >= 0",
            name="ck_meal_entries_macros",
        ),

        # Индекс для поиска записей пользователя по времени
        Index("ix_meal_entries_user_eaten_at", "user_id", "eaten_at"),
    )

    # Уникальный идентификатор записи
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Пользователь, которому принадлежит запись
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    # Дата и время приёма пищи
    eaten_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Тип приёма пищи
    meal_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Название или описание еды
    description: Mapped[str] = mapped_column(String(250), nullable=False)

    # Калорийность
    calories: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)

    # Белки, жиры и углеводы в граммах
    protein_g: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    fat_g: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    carbs_g: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)

    # Дополнительные заметки
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Время создания записи в базе данных
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )