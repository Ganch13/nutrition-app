from pwdlib import PasswordHash
import os
from datetime import datetime, timedelta, timezone
import jwt
from dotenv import load_dotenv
from typing import Annotated
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import get_db
from models import User


# Загружаем переменные окружения из файла .env.
load_dotenv()

# Получаем секретный ключ для подписи JWT.
SECRET_KEY = os.getenv("JWT_SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError(
        "Не задан JWT_SECRET_KEY в файле .env"
    )

# Алгоритм подписи токенов.
ALGORITHM = "HS256"

# Срок действия токена — 30 минут.
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Создаём объект для безопасного хеширования паролей.
# Библиотека выбирает рекомендуемые настройки алгоритма.
password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Преобразует исходный пароль в хеш для хранения в базе данных."""
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Проверяет, соответствует ли пароль сохранённому хешу."""
    return password_hash.verify(password, hashed_password)


def create_access_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    """Создаёт подписанный JWT с ограниченным сроком действия."""

    # Создаём копию данных, чтобы не изменять исходный словарь.
    to_encode = data.copy()

    # Определяем время окончания действия токена.
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # Добавляем в токен время окончания действия.
    to_encode.update({"exp": expire})

    # Подписываем токен секретным ключом и возвращаем строку.
    return jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


# Извлекаем Bearer-токен из заголовка Authorization.
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    db: Session = Depends(get_db),
) -> User:
    """Проверяет JWT и возвращает соответствующего пользователя."""

    # Без токена доступ запрещён.
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Не аутентифицирован",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        # Проверяем подпись и срок действия токена.
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        # В поле sub должен находиться идентификатор пользователя.
        subject = payload.get("sub")

        if not isinstance(subject, str) or not subject.isdigit():
            raise HTTPException(
                status_code=401,
                detail="Неверные учетные данные для аутентификации",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = int(subject)

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Недействительный или просроченный токен",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    # Проверяем, что пользователь с таким ID существует.
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user