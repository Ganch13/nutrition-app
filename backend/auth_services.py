"""Сессии входа: выдача, обновление и отзыв refresh-токенов, смена пароля (шаг 72).

Две части сессии:
  * access-токен (JWT) живёт 15 минут и передаётся в заголовке Authorization — им подписан каждый запрос;
  * refresh-токен живёт до 30 дней, лежит в HttpOnly-cookie и нужен только для получения нового
    access-токена. Его случайное значение в базе не хранится — только хеш.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models import PersonalAccessKey, RefreshToken, User
from security import hash_password, verify_password

# Сколько живёт refresh-токен (продлевается при каждом обновлении)
REFRESH_TOKEN_DAYS = 30

# Если уже погашенный токен пришёл в течение этих секунд, считаем это гонкой двух вкладок, а не кражей
REUSE_GRACE_SECONDS = 10

# Просроченные токены старше этого срока удаляются при следующем входе пользователя
CLEANUP_AFTER_DAYS = 7


class InvalidRefreshTokenError(Exception):
    # Токена нет, он неизвестен, просрочен, погашен или пользователь удалён
    pass


class WrongPasswordError(Exception):
    # При смене пароля неверно указан текущий
    pass


class SamePasswordError(Exception):
    # Новый пароль совпадает с текущим
    pass


def _hash(raw_token: str) -> str:
    """SHA-256 токена: "Xk3...abc" → 64 шестнадцатеричных символа. Токен случайный и длинный, медленный хеш не нужен."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def issue_refresh_token(db: Session, user_id: int, family_id: str | None = None) -> str:
    """Создаёт refresh-токен и возвращает его сырое значение (его кладут в cookie). В базе — только хеш.

    family_id=None начинает новую сессию (вход); при обновлении передаётся семья прежнего токена.
    """
    raw = secrets.token_urlsafe(48)  # 64 символа, 384 бита случайности
    now = _now()
    try:
        # Заодно убираем давно просроченные токены этого пользователя, чтобы таблица не росла
        db.execute(
            delete(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.expires_at < now - timedelta(days=CLEANUP_AFTER_DAYS),
            )
        )
        db.add(
            RefreshToken(
                user_id=user_id,
                family_id=family_id or uuid.uuid4().hex,
                token_hash=_hash(raw),
                expires_at=now + timedelta(days=REFRESH_TOKEN_DAYS),
            )
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return raw


def _revoke_family(db: Session, family_id: str, reason: str) -> None:
    """Гасит все ещё действующие токены семьи (одного входа)."""
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now(), revoked_reason=reason)
    )


def rotate_refresh_token(db: Session, raw_token: str | None) -> tuple[User, str | None]:
    """Обменивает refresh-токен на новый. Возвращает (пользователь, новый токен или None).

    Новый токен None означает «гонку вкладок»: старый токен только что заменила соседняя вкладка,
    браузер уже получил новый cookie, поэтому второй раз cookie менять не нужно — достаточно access-токена.
    Исключение InvalidRefreshTokenError — войти заново (токен неизвестен, просрочен или украден).
    """
    if not raw_token:
        raise InvalidRefreshTokenError

    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _hash(raw_token)))
    if token is None:
        raise InvalidRefreshTokenError

    now = _now()
    try:
        if token.revoked_at is not None:
            recently_rotated = (
                token.revoked_reason == "rotated"
                and now - token.revoked_at <= timedelta(seconds=REUSE_GRACE_SECONDS)
            )
            if recently_rotated:
                user = db.get(User, token.user_id)
                if user is None:
                    raise InvalidRefreshTokenError
                return user, None
            # Погашенный токен предъявлен позже: возможно, его украли. Гасим всю цепочку — вход заново
            _revoke_family(db, token.family_id, "reuse")
            db.commit()
            raise InvalidRefreshTokenError

        if token.expires_at <= now:
            raise InvalidRefreshTokenError

        user = db.get(User, token.user_id)
        if user is None:
            raise InvalidRefreshTokenError

        token.revoked_at = now
        token.revoked_reason = "rotated"
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    return user, issue_refresh_token(db, user.id, token.family_id)


def revoke_session(db: Session, raw_token: str | None) -> None:
    """Выход: гасит всю сессию, к которой относится токен. Неизвестный токен молча игнорируется."""
    if not raw_token:
        return
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _hash(raw_token)))
    if token is None:
        return
    try:
        _revoke_family(db, token.family_id, "logout")
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def change_password(db: Session, user: User, current_password: str, new_password: str) -> str:
    """Меняет пароль, гасит все сессии пользователя на всех устройствах и открывает новую на этом.

    Заодно отзывает все личные ключи доступа (быстрая команда iPhone): если пароль меняют из-за утечки,
    ключ тоже мог утечь. После смены пароля ключ для iPhone нужно создать заново.

    Возвращает refresh-токен для текущего устройства (чтобы человека не выкинуло из приложения).
    Ошибки: WrongPasswordError, SamePasswordError.
    """
    if user.password_hash is None or not verify_password(current_password, user.password_hash):
        raise WrongPasswordError
    if current_password == new_password:
        raise SamePasswordError
    try:
        user.password_hash = hash_password(new_password)
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_now(), revoked_reason="password")
        )
        db.execute(
            update(PersonalAccessKey)
            .where(PersonalAccessKey.user_id == user.id, PersonalAccessKey.revoked_at.is_(None))
            .values(revoked_at=_now(), revoked_reason="password")
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return issue_refresh_token(db, user.id)
