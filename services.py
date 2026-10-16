from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from models import Household, HouseholdMember, User, WeightRecord
from schemas import UserCreate, WeightRecordCreate
from sqlalchemy import select


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


class HouseholdNotFoundError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


class HouseholdMemberAlreadyExistsError(Exception):
    pass


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