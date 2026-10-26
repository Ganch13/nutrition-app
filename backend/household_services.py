"""Бизнес-логика приглашений и управления участниками домохозяйства (шаг 62)."""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models import Household, HouseholdInvite, HouseholdMember, User
from services import HouseholdMemberAlreadyExistsError

# Алфавит кода без похожих символов (нет 0/O, 1/I/L): код удобно диктовать по телефону.
# 31 символ, длина 8 → около 850 миллиардов вариантов.
INVITE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
INVITE_CODE_LENGTH = 8

# Срок жизни кода
INVITE_LIFETIME = timedelta(days=7)


class InvalidInviteError(Exception):
    """Код не найден, просрочен или уже использован (причину намеренно не различаем)."""


class InviteNotFoundError(Exception):
    """Приглашения с таким id нет в этом домохозяйстве или оно уже использовано."""


class MemberNotFoundError(Exception):
    """Такого участника в домохозяйстве нет."""


class OwnerProtectedError(Exception):
    """Владельца нельзя удалить, он не может выйти, его роль нельзя менять."""


class InsufficientRoleError(Exception):
    """У действующего пользователя недостаточно прав на это действие."""


def normalize_invite_code(raw_code: str) -> str:
    """Приводит введённый код к хранимому виду.

    Пример: "  k7m2-9qxp " → "K7M29QXP"
    Убираем пробелы и дефисы и делаем буквы заглавными, чтобы код можно
    было вводить как удобно.
    """
    return "".join(char for char in raw_code.upper() if char.isalnum())


def generate_invite_code() -> str:
    """Случайный код из безопасного генератора. Пример результата: "K7M29QXP".

    Используем secrets, а не random: random предсказуем, secrets предназначен
    для токенов и паролей.
    """
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))


def create_invite(db: Session, household_id: int, created_by_user_id: int) -> HouseholdInvite:
    """Создаёт код приглашения на 7 дней.

    Аргументы: household_id — например 1; created_by_user_id — например 1 (владелец).
    Результат: строка HouseholdInvite с кодом, например "K7M29QXP".
    """
    # Берём коды, пока не найдём свободный (на практике хватает одной попытки)
    while True:
        code = generate_invite_code()
        if db.scalar(select(HouseholdInvite.id).where(HouseholdInvite.code == code)) is None:
            break

    invite = HouseholdInvite(
        household_id=household_id,
        code=code,
        created_by_user_id=created_by_user_id,
        expires_at=datetime.now(timezone.utc) + INVITE_LIFETIME,
    )

    try:
        db.add(invite)
        db.commit()
        db.refresh(invite)
    except SQLAlchemyError:
        db.rollback()
        raise

    return invite


def list_active_invites(db: Session, household_id: int) -> list[HouseholdInvite]:
    """Действующие коды домохозяйства: не использованные и не просроченные, новые первыми."""
    now = datetime.now(timezone.utc)
    statement = (
        select(HouseholdInvite)
        .where(
            HouseholdInvite.household_id == household_id,
            HouseholdInvite.used_at.is_(None),
            HouseholdInvite.expires_at > now,
        )
        .order_by(HouseholdInvite.created_at.desc(), HouseholdInvite.id.desc())
    )
    return list(db.scalars(statement).all())


def revoke_invite(db: Session, household_id: int, invite_id: int) -> None:
    """Отзывает (удаляет) неиспользованный код.

    Пример: revoke_invite(db, 1, 5) — удалит приглашение 5 из домохозяйства 1.
    Код другого домохозяйства или уже использованный даёт InviteNotFoundError.
    """
    invite = db.get(HouseholdInvite, invite_id)

    # Проверка household_id важна: иначе администратор своей семьи
    # мог бы отозвать код чужой, зная его id
    if invite is None or invite.household_id != household_id or invite.used_at is not None:
        raise InviteNotFoundError()

    try:
        db.delete(invite)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def join_household(db: Session, user_id: int, raw_code: str) -> dict:
    """Добавляет пользователя в домохозяйство по коду.

    Аргументы: user_id — кто вступает, например 2; raw_code — например "k7m2-9qxp".
    Результат, например: {"id": 1, "name": "Дом", "created_at": datetime(...), "role": "member"}
    Ошибки: InvalidInviteError (нет / просрочен / использован),
            HouseholdMemberAlreadyExistsError (вы уже участник; код при этом не тратится).
    """
    code = normalize_invite_code(raw_code)

    # with_for_update() блокирует строку кода до конца транзакции: если двое введут
    # один код одновременно, второй дождётся первого и увидит used_at, а не вступит тоже.
    invite = db.scalar(
        select(HouseholdInvite).where(HouseholdInvite.code == code).with_for_update()
    )
    now = datetime.now(timezone.utc)

    if invite is None or invite.used_at is not None or invite.expires_at <= now:
        db.rollback()  # снимаем блокировку
        raise InvalidInviteError()

    # Запоминаем id до commit: после commit объект обновляется заново
    household_id = invite.household_id

    if db.get(HouseholdMember, (household_id, user_id)) is not None:
        db.rollback()
        raise HouseholdMemberAlreadyExistsError()

    # Вступление и пометка кода использованным: одна транзакция, всё или ничего
    invite.used_at = now
    invite.used_by_user_id = user_id

    try:
        db.add(HouseholdMember(household_id=household_id, user_id=user_id, role="member"))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    household = db.get(Household, household_id)
    return {
        "id": household.id,
        "name": household.name,
        "created_at": household.created_at,
        "role": "member",
    }


def change_member_role(
    db: Session,
    household_id: int,
    target_user_id: int,
    new_role: str,
) -> dict:
    """Меняет роль участника. Вызывающий уже проверен как владелец.

    Пример: change_member_role(db, 1, 2, "admin") → роль пользователя 2 станет "admin".
    Результат, например: {"household_id": 1, "user_id": 2, "name": "Леся",
                          "role": "admin", "joined_at": datetime(...)}
    """
    target = db.get(HouseholdMember, (household_id, target_user_id))

    if target is None:
        raise MemberNotFoundError()

    if target.role == "owner":
        raise OwnerProtectedError()

    target.role = new_role

    try:
        db.commit()
        db.refresh(target)
    except SQLAlchemyError:
        db.rollback()
        raise

    user = db.get(User, target_user_id)
    return {
        "household_id": target.household_id,
        "user_id": target.user_id,
        "name": user.name,
        "role": target.role,
        "joined_at": target.joined_at,
    }


def remove_member(
    db: Session,
    household_id: int,
    target_user_id: int,
    acting: HouseholdMember,
) -> None:
    """Удаляет участника из домохозяйства или даёт ему выйти самому.

    Аргументы: target_user_id — кого удаляем, например 2;
               acting — членство того, кто удаляет, например (user_id=1, role="owner").
    Правила:
      · выйти может любой участник, кроме владельца;
      · владелец удаляет любого, кроме себя;
      · администратор удаляет только обычных участников;
      · обычный участник удаляет только себя.
    Сам пользователь и его данные не удаляются, только членство.
    """
    target = db.get(HouseholdMember, (household_id, target_user_id))

    if target is None:
        raise MemberNotFoundError()

    is_self = target.user_id == acting.user_id
    allowed = (
        is_self
        or acting.role == "owner"
        or (acting.role == "admin" and target.role == "member")
    )

    if not allowed:
        raise InsufficientRoleError()

    # Владелец (в том числе сам вышедший) не удаляется: у домохозяйства всегда есть хозяин
    if target.role == "owner":
        raise OwnerProtectedError()

    try:
        db.delete(target)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise