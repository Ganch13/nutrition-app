from sqlalchemy import (UniqueConstraint, Date, CheckConstraint, DateTime,
                        ForeignKey, Integer, String, func,
                        text, Index, Numeric, Text, Boolean)
from sqlalchemy.dialects.postgresql import ARRAY
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

    # Блоки главной страницы, которые пользователь скрыл, например ["money", "weight"].
    # Вернуть блок можно в его разделе (деньги — в финансах, вес — в прогрессе и т. д.)
    home_hidden_blocks: Mapped[list[str]] = mapped_column(
        ARRAY(String(20)),
        nullable=False,
        server_default=text("'{}'"),
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

    # Согласие участника на совместное планирование питания (шаг 69): если включено,
    # семья видит его меню, его блюда попадают в общий список закупок и план готовки,
    # а совместное составление меню может создавать ему план. По умолчанию выключено.
    plans_together: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
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

    # Идентификатор серии для повторяющихся событий (например, «Работа пн–пт»).
    # У одиночных событий пусто. Пример значения: "3f2b8c1e-9a4d-4e57-b0a1-6d2f7c9e1a10".
    # Нужен, чтобы удалить всю серию одним действием.
    series_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )

    # True — блок-контейнер («Работа»): внутри него могут быть другие события (обед с 14 до 15).
    # Вложенным считается событие, целиком попадающее во время контейнера. Без контейнера
    # два события пересекаться не могут (проверяет schedule_services.check_overlaps)
    is_container: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
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

    # Номер суперсета внутри сессии. Блоки с одинаковым номером выполняются
    # вперемежку, поэтому им разрешено пересекаться по времени. Пусто — обычный блок.
    # Пример: у «Жим лёжа» и «Тяга блока» superset_group = 1.
    superset_group: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Когда пользователь нажал «Выполнил упражнение». Пусто — ещё не выполнено.
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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

    # Откуда взята запись: продукт справочника и съеденная масса.
    # Значения калорий и БЖУ выше — это СНИМОК на момент записи: если продукт
    # потом изменят или удалят, история питания не меняется (поэтому при удалении
    # продукта food_id становится пустым, а не удаляется вся запись).
    food_id: Mapped[int | None] = mapped_column(
        ForeignKey("foods.id", ondelete="SET NULL"),
        nullable=True,
    )
    amount_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)

    # Время создания записи в базе данных
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Food(Base):
    """Продукт справочника: пищевая ценность на 100 г и необязательная порция.

    Три вида продуктов:
      * встроенные — owner_user_id пусто, household_id пусто (общие для всех, только чтение);
      * личные — owner_user_id заполнен, household_id пусто (видит только автор);
      * семейные — household_id заполнен (видят все участники домохозяйства).
    """

    __tablename__ = "foods"

    __table_args__ = (
        CheckConstraint(
            "category IN ('meat', 'fish', 'eggs', 'dairy', 'grains', 'bakery', 'vegetables', "
            "'fruits', 'legumes', 'nuts', 'fats', 'sweets', 'drinks', 'sauces', 'supplements', 'other')",
            name="ck_foods_category",
        ),
        CheckConstraint(
            "calories_per_100g >= 0 AND calories_per_100g <= 900",
            name="ck_foods_calories",
        ),
        CheckConstraint(
            "protein_per_100g >= 0 AND fat_per_100g >= 0 AND carbs_per_100g >= 0 "
            "AND protein_per_100g + fat_per_100g + carbs_per_100g <= 100.5",
            name="ck_foods_macros",
        ),
        CheckConstraint(
            "serving_grams IS NULL OR serving_grams > 0",
            name="ck_foods_serving",
        ),
        Index("ix_foods_owner", "owner_user_id"),
        Index("ix_foods_household", "household_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Автор продукта; у встроенных пусто
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Семья, которой доступен продукт; у личных и встроенных пусто
    household_id: Mapped[int | None] = mapped_column(ForeignKey("households.id"), nullable=True)

    # Название для показа, например "Куриная грудка (готовая)"
    name: Mapped[str] = mapped_column(String(150), nullable=False)

    # Название для поиска: нижний регистр, «ё» заменена на «е». Поиск не зависит от локали базы
    search_name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)

    category: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'other'"))

    # Пищевая ценность на 100 г продукта
    calories_per_100g: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    protein_per_100g: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    fat_per_100g: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    carbs_per_100g: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)

    # Удобная порция, например «1 яйцо» = 55 г; обе колонки заполняются вместе или обе пусты
    serving_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    serving_grams: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class NutritionSettings(Base):
    """Личные настройки расчёта норм питания (шаг 66). Одна строка на пользователя."""

    __tablename__ = "nutrition_settings"

    __table_args__ = (
        CheckConstraint(
            "activity_level IN ('sedentary', 'light', 'moderate', 'active')",
            name="ck_nutrition_settings_activity",
        ),
        CheckConstraint("meals_per_day BETWEEN 3 AND 6", name="ck_nutrition_settings_meals"),
        CheckConstraint(
            "protein_g_per_kg IS NULL OR protein_g_per_kg BETWEEN 0.8 AND 3.5",
            name="ck_nutrition_settings_protein",
        ),
        CheckConstraint(
            "calorie_override IS NULL OR calorie_override BETWEEN 800 AND 6000",
            name="ck_nutrition_settings_calories",
        ),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)

    # Активность вне тренировок: sedentary — сидячая работа, light — немного ходьбы,
    # moderate — много ходьбы, active — тяжёлый физический труд
    activity_level: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'sedentary'"))

    # Сколько приёмов пищи в день планировать (3–6)
    meals_per_day: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("4"))

    # Свои значения вместо расчётных; пусто — считать автоматически
    protein_g_per_kg: Mapped[Decimal | None] = mapped_column(Numeric(3, 1), nullable=True)
    calorie_override: Mapped[int | None] = mapped_column(Integer, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Ledger(Base):
    """Финансовая книга: личная (принадлежит пользователю) или семейная (домохозяйству)."""

    __tablename__ = "ledgers"

    __table_args__ = (
        # Книга принадлежит либо пользователю, либо домохозяйству, но не обоим сразу
        CheckConstraint(
            """
            (user_id IS NOT NULL AND household_id IS NULL)
            OR (user_id IS NULL AND household_id IS NOT NULL)
            """,
            name="ck_ledgers_single_owner",
        ),
        # Код валюты ISO 4217 состоит из трёх букв, например EUR
        CheckConstraint("char_length(currency) = 3", name="ck_ledgers_currency_length"),
        CheckConstraint("cycle_mode IN ('calendar', 'income')", name="ck_ledgers_cycle_mode"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Владелец личной книги. unique: у пользователя может быть только одна личная книга
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        unique=True,
        nullable=True,
    )

    # Владелец семейной книги. unique: у домохозяйства может быть только одна книга
    household_id: Mapped[int | None] = mapped_column(
        ForeignKey("households.id"),
        unique=True,
        nullable=True,
    )

    # Код валюты книги, например "EUR"; после создания не меняется
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    # Как считать бюджетный период: calendar — календарный месяц, income — от дохода до дохода
    # (границы задают повторяющиеся доходы с отметкой «начинает цикл»)
    cycle_mode: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default=text("'calendar'"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class FinanceCategory(Base):
    """Категория операций внутри книги: расход или доход."""

    __tablename__ = "finance_categories"

    __table_args__ = (
        CheckConstraint("kind IN ('expense', 'income')", name="ck_finance_categories_kind"),
        # В одной книге не может быть двух одинаковых категорий одного типа
        UniqueConstraint("ledger_id", "kind", "name", name="uq_finance_categories_ledger_kind_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id"), nullable=False)

    # Название, например "Продукты"
    name: Mapped[str] = mapped_column(String(80), nullable=False)

    # Тип: expense (расход) или income (доход)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class FinanceTransaction(Base):
    """Операция: расход или доход (тип определяется категорией)."""

    __tablename__ = "finance_transactions"

    __table_args__ = (
        # Сумма всегда положительная; знак определяется типом категории
        CheckConstraint("amount > 0", name="ck_finance_transactions_amount_positive"),
        # Ускоряем выборку операций книги за период
        Index("ix_finance_transactions_ledger_date", "ledger_id", "occurred_on"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id"), nullable=False)

    category_id: Mapped[int] = mapped_column(
        ForeignKey("finance_categories.id"),
        nullable=False,
    )

    # Сумма в валюте книги, например Decimal("120.50")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Дата операции (без времени)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)

    description: Mapped[str | None] = mapped_column(String(250), nullable=True)

    # Сводка за период, строкой которой является операция («Продукты 8 000 за 1–7 ноября»); пусто — обычная операция.
    # Строки сводки удаляются вместе с ней (finance_summaries.delete_summary; CASCADE — страховка)
    summary_id: Mapped[int | None] = mapped_column(
        ForeignKey("finance_expense_summaries.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Кто внёс операцию (важно в семейной книге). Если автор удалил аккаунт, поле становится пустым:
    # операция остаётся в семейной книге, а в интерфейсе подписана «Удалённый пользователь»
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class FinanceExpenseSummary(Base):
    """Сводка расходов за период: несколько строк «категория — сумма», внесённых за один раз.

    Пункт 5 ТЗ от 29.10.2026: вместо отдельных покупок можно внести итог за день, неделю, месяц или свои даты.
    Сами строки — обычные операции (FinanceTransaction.summary_id) с датой period_end, поэтому баланс,
    отчёты, лимиты и цели считают их так же, как отдельные расходы.
    Пример: period_start=2026-10-20, period_end=2026-10-26, строки «Продукты 8 000», «Транспорт 1 200».
    """

    __tablename__ = "finance_expense_summaries"

    __table_args__ = (
        CheckConstraint("period_start <= period_end", name="ck_finance_expense_summaries_period"),
        Index("ix_finance_expense_summaries_ledger_period", "ledger_id", "period_start", "period_end"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id", ondelete="CASCADE"), nullable=False)

    # Первый и последний день периода (оба включаются)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    # Пояснение, например «Чеки за неделю»
    note: Mapped[str | None] = mapped_column(String(250), nullable=True)

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class FinanceBalanceAdjustment(Base):
    """Корректировка баланса книги: «на счетах на самом деле столько-то» без дохода и расхода.

    Хранится разница между фактическим остатком и тем, что насчитало приложение. Она входит
    только в «Всего» (баланс), но не в отчёты о доходах и расходах, лимиты и бюджетные периоды.
    Пример: приложение насчитало 50 000 ₽, человек ввёл 52 300 ₽ → amount = Decimal("2300.00").
    Если ввёл 49 000 ₽ → amount = Decimal("-1000.00").
    """

    __tablename__ = "finance_balance_adjustments"

    __table_args__ = (
        # Нулевая корректировка ничего не меняет, такую не сохраняем
        CheckConstraint("amount <> 0", name="ck_finance_balance_adjustments_amount_nonzero"),
        Index("ix_finance_balance_adjustments_ledger_date", "ledger_id", "adjusted_on"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Книга удаляется — её корректировки тоже
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id", ondelete="CASCADE"), nullable=False)

    # Разница со знаком: плюс — денег больше, чем насчитано, минус — меньше
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # День, на который сделана сверка (сегодня по часовому поясу пользователя)
    adjusted_on: Mapped[date] = mapped_column(Date, nullable=False)

    # Пояснение, например «сверка с банком»
    note: Mapped[str | None] = mapped_column(String(250), nullable=True)

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class FinanceBudget(Base):
    """Месячный лимит расходов на категорию."""

    __tablename__ = "finance_budgets"

    __table_args__ = (
        CheckConstraint("monthly_limit > 0", name="ck_finance_budgets_limit_positive"),
        # На категорию в книге может быть только один лимит
        UniqueConstraint("ledger_id", "category_id", name="uq_finance_budgets_ledger_category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id"), nullable=False)

    category_id: Mapped[int] = mapped_column(
        ForeignKey("finance_categories.id"),
        nullable=False,
    )

    monthly_limit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)


class FinanceRecurringRule(Base):
    """Правило повторяющейся операции: регулярный доход (зарплата, аванс) или обязательный платёж (аренда, кредит).

    Пример строки: name="Зарплата", amount=50000, frequency="semimonthly", day_of_month=10,
    second_day_of_month=25, start_on=2026-10-10, auto_post=False, is_primary=True.
    Операция (FinanceTransaction) создаётся по правилу после подтверждения «Получено» / «Оплачено».
    Автоматически (auto_post) могут списываться только обязательные платежи: доход не начисляется сам,
    приложение спрашивает «Поступил ли платёж?». Тип (доход или расход) определяет категория правила.
    """

    __tablename__ = "finance_recurring_rules"

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_finance_rules_amount_positive"),
        CheckConstraint(
            "frequency IN ('weekly', 'biweekly', 'semimonthly', 'monthly', 'yearly')",
            name="ck_finance_rules_frequency",
        ),
        CheckConstraint(
            "day_of_month IS NULL OR day_of_month BETWEEN 1 AND 31",
            name="ck_finance_rules_day_of_month",
        ),
        CheckConstraint(
            "second_day_of_month IS NULL OR second_day_of_month BETWEEN 1 AND 31",
            name="ck_finance_rules_second_day",
        ),
        CheckConstraint("end_on IS NULL OR end_on >= start_on", name="ck_finance_rules_period"),
        Index("ix_finance_rules_ledger", "ledger_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id", ondelete="CASCADE"), nullable=False)

    # Категория создаваемых операций; по ней определяется, доход это или расход
    category_id: Mapped[int] = mapped_column(ForeignKey("finance_categories.id"), nullable=False)

    # Название для человека, например "Аренда квартиры"
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Плановая сумма в валюте книги
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Как часто повторяется: weekly (каждую неделю), biweekly (раз в две недели),
    # semimonthly (два раза в месяц: day_of_month и second_day_of_month),
    # monthly (раз в месяц в день day_of_month), yearly (раз в год в день start_on)
    frequency: Mapped[str] = mapped_column(String(12), nullable=False)

    # Первая дата правила; для weekly/biweekly/yearly служит точкой отсчёта
    start_on: Mapped[date] = mapped_column(Date, nullable=False)

    # День месяца для monthly и первый день для semimonthly (1–31; в коротких месяцах — последний день)
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Второй день месяца для semimonthly, например 25 (аванс 10-го, зарплата 25-го)
    second_day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Последняя дата действия правила (только у платежей, например последний платёж по кредиту);
    # пусто — действует бессрочно. У доходов не задаётся: период заканчивается следующим основным доходом
    end_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    # True — платёж списывается сам в день выплаты; False — нужно подтвердить вручную. У доходов всегда False
    auto_post: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    # Основной (True) или дополнительный (False) доход или платёж. Границы бюджетного периода
    # задают только основные доходы; дополнительные (мелкие, нерегулярные) входят лишь в сумму периода
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    # False — правило на паузе: не создаёт операций и не влияет на планирование
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class FinanceRecurringOccurrence(Base):
    """Отметка «это повторение правила уже обработано»: оплачено/получено или пропущено.

    Пример строки: rule_id=3, due_on=2026-11-10, status="posted", transaction_id=57.
    Пока отметки нет, повторение считается ожидаемым (pending). Пара (rule_id, due_on) уникальна,
    поэтому две одновременные обработки не создадут одну и ту же операцию дважды.
    """

    __tablename__ = "finance_recurring_occurrences"

    __table_args__ = (
        UniqueConstraint("rule_id", "due_on", name="uq_finance_occurrences_rule_due"),
        CheckConstraint("status IN ('posted', 'skipped')", name="ck_finance_occurrences_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    rule_id: Mapped[int] = mapped_column(
        ForeignKey("finance_recurring_rules.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Плановая дата выплаты по правилу
    due_on: Mapped[date] = mapped_column(Date, nullable=False)

    # posted — операция создана; skipped — пропущено (операции нет)
    status: Mapped[str] = mapped_column(String(10), nullable=False)

    # Созданная операция. Если её удалили, отметка не пропадает, а становится skipped (см. delete_transaction)
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("finance_transactions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class FinancialGoal(Base):
    """Финансовая цель: накопление, простой долг или кредит с процентами.

    Личная цель лежит в личной книге пользователя, совместная в семейной книге домохозяйства:
    её видят и пополняют все участники семьи. Смысл полей зависит от kind:
      savings — target_amount это цель, start_amount уже накоплено;
      debt    — target_amount исходный долг, start_amount уже выплачено;
      loan    — target_amount текущий основной долг, start_amount всегда 0,
                interest_rate годовая ставка в процентах, payment_day день ежемесячного платежа.
    """

    __tablename__ = "finance_goals"

    __table_args__ = (
        CheckConstraint("kind IN ('savings', 'debt', 'loan')", name="ck_finance_goals_kind"),
        CheckConstraint("target_amount > 0", name="ck_finance_goals_target_positive"),
        CheckConstraint("start_amount >= 0", name="ck_finance_goals_start_non_negative"),
        CheckConstraint(
            "interest_rate IS NULL OR (interest_rate >= 0 AND interest_rate <= 1000)",
            name="ck_finance_goals_rate",
        ),
        CheckConstraint(
            "payment_day IS NULL OR payment_day BETWEEN 1 AND 31",
            name="ck_finance_goals_payment_day",
        ),
        # У кредита ставка и день платежа обязательны
        CheckConstraint(
            "kind <> 'loan' OR (interest_rate IS NOT NULL AND payment_day IS NOT NULL)",
            name="ck_finance_goals_loan_fields",
        ),
        Index("ix_finance_goals_ledger", "ledger_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id", ondelete="CASCADE"), nullable=False)

    kind: Mapped[str] = mapped_column(String(10), nullable=False)

    name: Mapped[str] = mapped_column(String(100), nullable=False)

    target_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    start_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        server_default=text("0"),
    )

    # Годовая ставка кредита в процентах, например 60 или 18.5
    interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)

    # День месяца ежемесячного платежа по кредиту (1–31)
    payment_day: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Кто создал цель; при удалении аккаунта поле очищается, цель остаётся семье
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class FinancialGoalEntry(Base):
    """Взнос в цель или платёж по долгу/кредиту.

    Для кредита сервер сам делит платёж: interest_part уходит банку, principal_part уменьшает долг,
    balance_after хранит остаток основного долга после платежа. Пример для долга 100 000 ₽ под 60%:
    amount=20000, interest_part=5000, principal_part=15000, balance_after=85000.
    Для накопления и простого долга эти три поля пустые.
    """

    __tablename__ = "finance_goal_entries"

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_finance_goal_entries_amount_positive"),
        Index("ix_finance_goal_entries_goal_date", "goal_id", "paid_on"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    goal_id: Mapped[int] = mapped_column(
        ForeignKey("finance_goals.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Автор взноса: по нему на совместной цели делится прогресс-бар
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    paid_on: Mapped[date] = mapped_column(Date, nullable=False)

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    interest_part: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    principal_part: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    balance_after: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    note: Mapped[str | None] = mapped_column(String(250), nullable=True)

    # Расход, из которого создана запись (пункт 2 ТЗ от 29.10.2026): «Расход 5 000 → цель „Отпуск“».
    # Пусто — взнос внесён вручную в самой цели. Одна операция даёт не больше одной записи (unique).
    # Правка и удаление такой записи идут только через операцию (finance_transactions.py);
    # CASCADE — страховка, чтобы запись не пережила свою операцию.
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("finance_transactions.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class HouseholdInvite(Base):
    """Одноразовый код приглашения в домохозяйство.

    Пример строки таблицы:
        id=1, household_id=1, code="K7M29QXP", created_by_user_id=1,
        created_at=2026-10-26 10:00, expires_at=2026-11-02 10:00,
        used_at=None, used_by_user_id=None
    Пока used_at пустой и срок не вышел, код можно использовать.
    """

    __tablename__ = "household_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # В какое домохозяйство приглашают, например 1.
    # index=True ускоряет запрос «все коды этого домохозяйства»
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id"),
        nullable=False,
        index=True,
    )

    # Сам код, например "K7M29QXP". unique: двух одинаковых кодов быть не может
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)

    # Кто создал код (владелец или администратор), например 1
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # До какого момента код действует, например 2026-11-02 10:00
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Когда код использовали; None — ещё не использован
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Кто воспользовался кодом, например 2; None — никто
    used_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Recipe(Base):
    """Рецепт: набор продуктов на ОДНУ порцию (шаг 67).

    Как и продукты, рецепты бывают встроенными (владельца нет), личными и семейными.
    Количество порций при готовке и закупке считается из плана питания (шаг 68).
    """

    __tablename__ = "recipes"

    __table_args__ = (
        CheckConstraint("prep_minutes BETWEEN 0 AND 600", name="ck_recipes_prep_minutes"),
        CheckConstraint("keeps_days BETWEEN 1 AND 7", name="ck_recipes_keeps_days"),
        Index("ix_recipes_owner", "owner_user_id"),
        Index("ix_recipes_household", "household_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Автор рецепта; у встроенных пусто
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Семья, которой доступен рецепт; у личных и встроенных пусто
    household_id: Mapped[int | None] = mapped_column(ForeignKey("households.id"), nullable=True)

    name: Mapped[str] = mapped_column(String(150), nullable=False)

    # Название для поиска: нижний регистр, «ё» → «е»
    search_name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)

    # Для каких приёмов пищи подходит, через запятую: "lunch,dinner"
    meal_types: Mapped[str] = mapped_column(String(60), nullable=False)

    # Можно ли взять с собой и съесть на работе без разогрева сложных блюд
    portable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    # Сколько минут занимает готовка одной порции и сколько дней блюдо хранится в холодильнике
    prep_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("15"))
    keeps_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("2"))

    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class RecipeIngredient(Base):
    """Ингредиент рецепта: продукт справочника и масса на одну порцию."""

    __tablename__ = "recipe_ingredients"

    __table_args__ = (
        CheckConstraint("amount_g > 0", name="ck_recipe_ingredients_amount"),
        # Один продукт встречается в рецепте один раз
        UniqueConstraint("recipe_id", "food_id", name="uq_recipe_ingredients_recipe_food"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # RESTRICT: продукт, который используется в рецепте, удалить нельзя
    # (приложение заранее проверяет это и отвечает понятным сообщением)
    food_id: Mapped[int] = mapped_column(
        ForeignKey("foods.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    amount_g: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)

    # Порядок показа ингредиентов
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class PlannedMeal(Base):
    """Запланированный приём пищи в недельном плане питания (шаг 67).

    Значения калорий и БЖУ — снимок на момент планирования (как у MealEntry):
    правка рецепта или продукта не меняет уже составленный план.
    """

    __tablename__ = "planned_meals"

    __table_args__ = (
        CheckConstraint("meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')", name="ck_planned_meals_meal_type"),
        CheckConstraint("location IN ('home', 'work', 'away')", name="ck_planned_meals_location"),
        CheckConstraint("status IN ('planned', 'eaten', 'skipped')", name="ck_planned_meals_status"),
        CheckConstraint("portion_scale > 0", name="ck_planned_meals_scale"),
        Index("ix_planned_meals_user_date", "user_id", "plan_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # День плана в часовом поясе пользователя
    plan_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Во сколько запланирован приём пищи
    planned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    meal_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Где будет приём пищи: home — дома, work — на работе, away — вне дома (кафе, гости)
    location: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'home'"))

    # planned — в плане, eaten — съеден (создана запись MealEntry), skipped — пропущен
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'planned'"))

    # Рецепт-источник; пусто, если приём пищи собран вручную из продуктов или рецепт удалён
    recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True)

    title: Mapped[str] = mapped_column(String(200), nullable=False)

    # Во сколько раз порция больше или меньше порции из рецепта: 1.00 — как в рецепте
    portion_scale: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("1"))

    calories: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    protein_g: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    fat_g: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    carbs_g: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Запись о съеденном, созданная кнопкой «Съел»
    meal_entry_id: Mapped[int | None] = mapped_column(ForeignKey("meal_entries.id", ondelete="SET NULL"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PlannedMealItem(Base):
    """Продукт внутри запланированного приёма пищи (снимок названия, массы и пищевой ценности)."""

    __tablename__ = "planned_meal_items"

    __table_args__ = (CheckConstraint("amount_g > 0", name="ck_planned_meal_items_amount"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    planned_meal_id: Mapped[int] = mapped_column(
        ForeignKey("planned_meals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Если продукт потом удалят, строка остаётся с названием и значениями
    food_id: Mapped[int | None] = mapped_column(ForeignKey("foods.id", ondelete="SET NULL"), nullable=True)

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    amount_g: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    calories: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    protein_g: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    fat_g: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    carbs_g: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)


class ShoppingCheck(Base):
    """Отметка «куплено» в списке закупок (шаг 68).

    Строка существует — продукт отмечен. Отметки привязаны к области списка (scope_key:
    "u:5" — личный список пользователя 5; для семейного списка позже будет "h:3"),
    к дате начала периода и к ключу продукта ("food:12" или "name:хлеб").
    """

    __tablename__ = "shopping_checks"

    __table_args__ = (
        UniqueConstraint("scope_key", "range_start", "item_key", name="uq_shopping_checks_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope_key: Mapped[str] = mapped_column(String(20), nullable=False)
    range_start: Mapped[date] = mapped_column(Date, nullable=False)
    item_key: Mapped[str] = mapped_column(String(100), nullable=False)

    # Кто поставил отметку (в семейном списке видно, кто купил)
    checked_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ProgressPhoto(Base):
    """Фото прогресса (шаг 70). Сам файл лежит на диске, в базе — только данные о нём.

    storage_name — случайное имя файла ("3f2a9c...e1.jpg"), которое создаёт сервер; из имени,
    присланного пользователем, ничего не берётся. Путь к файлу: <UPLOAD_DIR>/progress/<user_id>/<storage_name>.
    """

    __tablename__ = "progress_photos"

    __table_args__ = (
        CheckConstraint(
            "angle IN ('front', 'side', 'back', 'other')",
            name="ck_progress_photos_angle",
        ),
        Index("ix_progress_photos_user_date", "user_id", "taken_on"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Дата съёмки (не загрузки): по ней фото выстраиваются в хронологию
    taken_on: Mapped[date] = mapped_column(Date, nullable=False)

    # Ракурс: спереди, сбоку, сзади или другое
    angle: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'front'"))

    note: Mapped[str | None] = mapped_column(String(300), nullable=True)

    storage_name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class RefreshToken(Base):
    """Долгоживущая «сессия» входа (шаг 72). Позволяет не вводить пароль каждые 15 минут.

    В базе лежит только SHA-256 от токена (token_hash), как и с паролями: утечка базы не даёт войти.
    Сам токен хранится в cookie браузера (HttpOnly — скрипты страницы его не видят).
    При каждом обновлении старый токен погашается и выдаётся новый той же «семьи» (family_id);
    если погашённый токен предъявлен снова, значит его украли, и гасится вся семья.
    """

    __tablename__ = "refresh_tokens"

    __table_args__ = (
        Index("ix_refresh_tokens_user", "user_id"),
        Index("ix_refresh_tokens_family", "family_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Общий идентификатор всех токенов одного входа (цепочки обновлений)
    family_id: Mapped[str] = mapped_column(String(32), nullable=False)

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Когда токен погашен и почему: "rotated" (заменён новым), "logout", "password", "reuse"
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(10), nullable=True)
