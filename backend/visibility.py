"""Общие правила видимости записей «встроенные / личные / семейные».

Используется продуктами (Food) и рецептами (Recipe): у обоих есть колонки
owner_user_id (автор) и household_id (семья).
"""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from models import HouseholdMember

# Роли домохозяйства, которым разрешено менять и удалять чужие семейные записи
MANAGER_ROLES = ("owner", "admin")


def household_ids_of(db: Session, user_id: int) -> list[int]:
    """id всех домохозяйств пользователя, например [1, 3]."""
    return list(db.scalars(select(HouseholdMember.household_id).where(HouseholdMember.user_id == user_id)).all())


def visible_clause(model, user_id: int, household_ids: list[int]):
    """Условие SQL «запись видна пользователю»: встроенная, своя или семейная."""
    conditions = [
        model.owner_user_id.is_(None) & model.household_id.is_(None),
        model.owner_user_id == user_id,
    ]
    if household_ids:
        conditions.append(model.household_id.in_(household_ids))
    return or_(*conditions)


def source_of(item) -> str:
    """builtin — встроенная, household — семейная, personal — личная."""
    if item.owner_user_id is None and item.household_id is None:
        return "builtin"
    return "household" if item.household_id is not None else "personal"


def can_edit(db: Session, user_id: int, item) -> bool:
    """Может ли пользователь менять запись.

    Встроенные — никто. Личные — автор. Семейные — автор, а также владелец и администратор семьи.
    """
    if source_of(item) == "builtin":
        return False
    if item.owner_user_id == user_id:
        return True
    if item.household_id is not None:
        membership = db.get(HouseholdMember, (item.household_id, user_id))
        return membership is not None and membership.role in MANAGER_ROLES
    return False
