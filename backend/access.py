"""Общие проверки доступа к домохозяйствам.

Вынесено из main.py, чтобы ими могли пользоваться и main.py, и household_routes.py
(main подключает роутер, поэтому роутер не должен импортировать main).
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import Household, HouseholdMember, User


def require_household_member(
    household_id: int,
    db: Session,
    current_user: User,
    allowed_roles: tuple[str, ...] | None = None,
) -> HouseholdMember:
    """Проверяет членство пользователя и, при необходимости, его роль.

    Пример вызова: require_household_member(1, db, current_user, ("owner", "admin"))
    Результат: строка HouseholdMember, например (household_id=1, user_id=2, role="admin").
    Ошибки: 404 — домохозяйства нет; 403 — вы не участник или роль не подходит.
    """

    membership = db.get(
        HouseholdMember,
        (household_id, current_user.id),
    )

    if db.get(Household, household_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Домохозяйство не найдено",
        )

    if membership is None:
        raise HTTPException(
            status_code=403,
            detail="Нет доступа к этому домохозяйству",
        )

    if (
        allowed_roles is not None
        and membership.role not in allowed_roles
    ):
        raise HTTPException(
            status_code=403,
            detail="Недостаточно прав для выполнения действия",
        )

    return membership