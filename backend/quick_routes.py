"""Эндпоинты личных ключей и быстрого добавления расхода с iPhone (ТЗ 29.10.26(2), часть 2).

Два набора адресов с разной авторизацией:
  * /access-keys — управление ключами из «Профиль и настройки». Только обычный вход (JWT access-токен);
    ключ lad_... здесь не работает: это не JWT, get_current_user ответит 401;
  * /quick/... — быстрая команда iPhone. Только личный ключ: Authorization: Bearer lad_...;
    JWT здесь не работает. Ключ даёт доступ только к этим адресам.
На сервере перед адресами стоит /api (Caddy): https://домен/api/quick/expense.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from database import get_db
from error_handling import register_error_map
from models import PersonalAccessKey, User
from quick_services import (
    AccessKeyLimitError,
    AccessKeyNotFoundError,
    InvalidAccessKeyError,
    MAX_ACTIVE_KEYS,
    QuickAmountError,
    QuickHouseholdChoiceError,
    QuickLedgerNotFoundError,
    create_access_key,
    find_active_key,
    list_access_keys,
    quick_categories,
    quick_expense,
    revoke_access_key,
    touch_key,
)
from rate_limit import QUICK_BY_ADDRESS, QUICK_BY_KEY, client_address
from schemas import (
    AccessKeyCreate,
    AccessKeyCreatedResponse,
    AccessKeyResponse,
    QuickCategoriesResponse,
    QuickExpenseCreate,
    QuickExpenseResponse,
    QuickLedgerKind,
)
from security import bearer_scheme, get_current_user

logger = logging.getLogger(__name__)

ERROR_RESPONSES = {
    AccessKeyLimitError: (
        409,
        f"Действующих ключей уже {MAX_ACTIVE_KEYS}: отзовите ненужный, чтобы создать новый",
    ),
    AccessKeyNotFoundError: (404, "Ключ не найден"),
    QuickAmountError: (422, "Сумма должна быть больше нуля"),
    QuickLedgerNotFoundError: (404, "Финансы этой книги не включены: включите их в разделе «Финансы»"),
    QuickHouseholdChoiceError: (422, "Вы состоите в нескольких семьях: укажите household_id"),
}


def register_error_handlers(app: FastAPI) -> None:
    """Подключает преобразование ошибок ключей и быстрого добавления в HTTP-ответы."""
    register_error_map(app, ERROR_RESPONSES)


# ---------------------------------------------------------------------------
# Управление ключами (обычный вход)
# ---------------------------------------------------------------------------

keys_router = APIRouter(prefix="/access-keys", tags=["access-keys"])


@keys_router.get("", response_model=list[AccessKeyResponse])
def list_keys_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ключи пользователя: название, начало ключа, даты и статус. Самих ключей в ответе нет."""
    return list_access_keys(db, current_user)


@keys_router.post("", response_model=AccessKeyCreatedResponse, status_code=201)
def create_key_endpoint(
    data: AccessKeyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Создаёт ключ. Запрос: {"name": "iPhone"}.

    Ответ 201 содержит поле "key" — ключ целиком, например "lad_Xk3f9Q...". Он показывается ОДИН раз:
    в базе только его хеш, поэтому повторно узнать ключ нельзя (только создать новый).
    409 — уже 5 действующих ключей.
    """
    return create_access_key(db, current_user, data.name)


@keys_router.delete("/{key_id}", response_model=AccessKeyResponse)
def revoke_key_endpoint(
    key_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Отзывает ключ: запросы с ним сразу получают 401. Ключ остаётся в списке со статусом «отозван»."""
    return revoke_access_key(db, current_user, key_id)


# ---------------------------------------------------------------------------
# Быстрое добавление (личный ключ)
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/quick", tags=["quick"])


@dataclass
class QuickContext:
    """Кто прислал быстрый запрос: ключ и его владелец."""

    key: PersonalAccessKey
    user: User


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Ключ доступа неверный или отозван. Создайте новый в «Профиль и настройки».",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_key_context(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Session = Depends(get_db),
) -> QuickContext:
    """Зависимость быстрых эндпоинтов: проверяет личный ключ и лимиты частоты.

    Порядок:
      1. лимит по адресу (60 запросов в минуту, считая неверные ключи) — защита от перебора;
      2. ключ: только формат lad_..., известный и не отозванный, иначе 401;
      3. лимит по ключу (30 запросов в минуту), иначе 429;
      4. дата последнего использования ключа.
    В журнал пишется только начало ключа (key_prefix), сам ключ — никогда.
    """
    address = client_address(request)
    QUICK_BY_ADDRESS.check(address)
    QUICK_BY_ADDRESS.hit(address)

    if credentials is None:
        raise _unauthorized()
    try:
        key, user = find_active_key(db, credentials.credentials)
    except InvalidAccessKeyError:
        raise _unauthorized() from None

    limit_key = str(key.id)
    QUICK_BY_KEY.check(limit_key)
    QUICK_BY_KEY.hit(limit_key)

    touch_key(db, key)
    logger.info("Быстрый запрос %s по ключу %s… пользователя %s", request.url.path, key.key_prefix, user.id)
    return QuickContext(key=key, user=user)


def get_quick_today(context: QuickContext = Depends(get_key_context)) -> date:
    """Сегодняшняя дата по часовому поясу владельца ключа. Тесты подменяют эту зависимость."""
    try:
        zone = ZoneInfo(context.user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    return datetime.now(zone).date()


@router.post("/expense", response_model=QuickExpenseResponse)
def quick_expense_endpoint(
    data: QuickExpenseCreate,
    context: QuickContext = Depends(get_key_context),
    today: date = Depends(get_quick_today),
    db: Session = Depends(get_db),
    idempotency_key: Annotated[str | None, Header(max_length=100)] = None,
):
    """Записывает расход одним запросом. Заголовок: Authorization: Bearer lad_...

    Тело: {"amount": 350, "category": "Продукты", "comment": "Пятёрочка", "date": "2026-10-29", "ledger": "personal"}
    (обязательна только сумма). Необязательный заголовок Idempotency-Key: повтор с тем же значением в течение
    10 минут не создаёт второй расход, а возвращает прежний ("duplicate": true).
    Ответ 200: {"ok": true, "amount": "350.00", "category": "Продукты", "balance": "12000.00", "free": "8000.00",
    "daily_allowance": "1142.86", "message": "Записано 350 ₽, «Продукты». Баланс ...", ...}
    Ошибки: 401 — ключ неверный или отозван; 422 — сумма ≤ 0; 404 — книга не включена; 429 — слишком часто.
    """
    return quick_expense(db, context.key, context.user, data, today, idempotency_key)


@router.get("/categories", response_model=QuickCategoriesResponse)
def quick_categories_endpoint(
    ledger: Annotated[QuickLedgerKind, Query()] = "personal",
    household_id: Annotated[int | None, Query(gt=0)] = None,
    context: QuickContext = Depends(get_key_context),
    db: Session = Depends(get_db),
):
    """Категории расходов книги для меню быстрой команды (только чтение).

    GET /quick/categories?ledger=personal → {"ledger": "personal", "names": ["Продукты", ...], "categories": [...]}
    """
    return quick_categories(db, context.user, ledger, household_id)
