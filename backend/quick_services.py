"""Личные ключи доступа и быстрое добавление расхода с iPhone (ТЗ 29.10.26(2), часть 2).

Зачем: открывать приложение ради одной покупки долго. Быстрая команда iPhone спрашивает сумму и категорию
и отправляет расход одним запросом с личным ключом:
    POST /api/quick/expense   Authorization: Bearer lad_Xk3f9Q...   {"amount": 350, "category": "Продукты"}

Как устроены ключи:
  * ключ создаётся в «Профиль и настройки» и показывается ОДИН раз: "lad_" + 43 случайных символа (32 байта);
  * в базе только SHA-256 ключа (key_hash) и начало для узнавания (key_prefix, "lad_Xk3f9Q");
  * ключ работает ТОЛЬКО на /quick/... — обычные эндпоинты ждут JWT и ключ не примут (это не JWT → 401);
  * отозванный ключ перестаёт работать сразу; смена пароля отзывает все ключи, удаление аккаунта их удаляет;
  * не больше MAX_ACTIVE_KEYS действующих ключей на пользователя.

Расход создаётся той же функцией, что и в обычной форме (finance_transactions.add_transaction), поэтому
баланс, «свободно», «в день», цели и периоды считают его точно так же, как введённый вручную.
"""

import hashlib
import secrets
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from finance_format import money, short_date
from finance_planning import spending_plan
from finance_recurring import sync_recurring
from finance_services import LedgerAccess, get_ledger_access, list_ledgers
from finance_transactions import add_transaction
from models import FinanceCategory, FinanceTransaction, PersonalAccessKey, QuickAddRequest, User
from schemas import FinanceTransactionCreate, QuickExpenseCreate

# Начало каждого ключа: по нему сразу видно, что это ключ «Лада», а не JWT
KEY_PREFIX = "lad_"

# Сколько случайных байт в ключе (32 байта = 256 бит, в тексте 43 символа)
KEY_RANDOM_BYTES = 32

# Длина начала ключа, которое хранится для узнавания: "lad_" + 6 символов
KEY_PREFIX_LENGTH = len(KEY_PREFIX) + 6

# Сколько действующих (не отозванных) ключей может быть у одного пользователя
MAX_ACTIVE_KEYS = 5

# Сколько минут повтор с тем же Idempotency-Key возвращает прежний расход вместо нового
QUICK_IDEMPOTENCY_MINUTES = 10

# Категория, куда попадает расход, если категорию из запроса не нашли (создаётся сама при первой нужде)
NO_CATEGORY_NAME = "Без категории"


class AccessKeyLimitError(Exception):
    # Уже MAX_ACTIVE_KEYS действующих ключей
    pass


class AccessKeyNotFoundError(Exception):
    # Ключа нет или он чужой
    pass


class InvalidAccessKeyError(Exception):
    # Ключ неизвестен, отозван или его владелец удалён
    pass


class QuickAmountError(Exception):
    # Сумма меньше или равна нулю
    pass


class QuickLedgerNotFoundError(Exception):
    # Нужная книга (личная или семейная) не включена
    pass


class QuickHouseholdChoiceError(Exception):
    # Семей несколько, а household_id не указан
    pass


def hash_key(raw_key: str) -> str:
    """SHA-256 ключа: "lad_Xk3f..." → 64 шестнадцатеричных символа. Ключ случайный и длинный, медленный хеш не нужен."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def key_to_dict(key: PersonalAccessKey) -> dict:
    """Ключ в формате ответа API (AccessKeyResponse), без самого ключа.

    Пример: {"id": 1, "name": "iPhone", "key_prefix": "lad_Xk3f9Q", "created_at": ..., "last_used_at": None,
             "revoked_at": None, "active": True}
    """
    return {
        "id": key.id,
        "name": key.name,
        "key_prefix": key.key_prefix,
        "created_at": key.created_at,
        "last_used_at": key.last_used_at,
        "revoked_at": key.revoked_at,
        "active": key.revoked_at is None,
    }


# ---------------------------------------------------------------------------
# Управление ключами (по обычному входу, не по ключу)
# ---------------------------------------------------------------------------


def create_access_key(db: Session, user: User, name: str) -> dict:
    """Создаёт ключ и возвращает его вместе с самим ключом — единственный раз, когда ключ виден целиком.

    Пример: name="iPhone" → {"id": 1, "name": "iPhone", "key_prefix": "lad_Xk3f9Q", ...,
                              "key": "lad_Xk3f9Q...43 символа"}
    Ошибка AccessKeyLimitError (409), если действующих ключей уже MAX_ACTIVE_KEYS.
    """
    active = db.scalar(
        select(func.count(PersonalAccessKey.id)).where(
            PersonalAccessKey.user_id == user.id,
            PersonalAccessKey.revoked_at.is_(None),
        )
    )
    if active >= MAX_ACTIVE_KEYS:
        raise AccessKeyLimitError

    raw_key = KEY_PREFIX + secrets.token_urlsafe(KEY_RANDOM_BYTES)  # "lad_" + 43 символа
    key = PersonalAccessKey(
        user_id=user.id,
        name=name,
        key_hash=hash_key(raw_key),
        key_prefix=raw_key[:KEY_PREFIX_LENGTH],
    )
    try:
        db.add(key)
        db.commit()
        db.refresh(key)
    except SQLAlchemyError:
        db.rollback()
        raise
    return {**key_to_dict(key), "key": raw_key}


def list_access_keys(db: Session, user: User) -> list[dict]:
    """Ключи пользователя: сначала действующие, затем отозванные, внутри — новые выше."""
    keys = db.scalars(
        select(PersonalAccessKey)
        .where(PersonalAccessKey.user_id == user.id)
        .order_by(PersonalAccessKey.revoked_at.is_not(None), PersonalAccessKey.id.desc())
    ).all()
    return [key_to_dict(key) for key in keys]


def revoke_access_key(db: Session, user: User, key_id: int) -> dict:
    """Отзывает ключ: с этой секунды запросы с ним получают 401. Повторный отзыв ничего не меняет.

    Чужой или несуществующий ключ — AccessKeyNotFoundError (404). Возвращает ключ в формате списка.
    """
    key = db.get(PersonalAccessKey, key_id)
    if key is None or key.user_id != user.id:
        raise AccessKeyNotFoundError
    if key.revoked_at is None:
        try:
            key.revoked_at = _now()
            key.revoked_reason = "manual"
            db.commit()
            db.refresh(key)
        except SQLAlchemyError:
            db.rollback()
            raise
    return key_to_dict(key)


# ---------------------------------------------------------------------------
# Проверка ключа на быстрых эндпоинтах
# ---------------------------------------------------------------------------


def find_active_key(db: Session, raw_key: str) -> tuple[PersonalAccessKey, User]:
    """Находит действующий ключ по его значению и возвращает (ключ, владелец).

    Ищем по хешу: сравнение идёт в базе по SHA-256, сам ключ нигде не сохраняется и не пишется в журнал.
    Неизвестный, отозванный ключ или ключ без префикса "lad_" — InvalidAccessKeyError (401).
    """
    if not raw_key.startswith(KEY_PREFIX):
        raise InvalidAccessKeyError
    key = db.scalar(select(PersonalAccessKey).where(PersonalAccessKey.key_hash == hash_key(raw_key)))
    if key is None or key.revoked_at is not None:
        raise InvalidAccessKeyError
    user = db.get(User, key.user_id)
    if user is None:
        raise InvalidAccessKeyError
    return key, user


def touch_key(db: Session, key: PersonalAccessKey) -> None:
    """Записывает дату последнего использования ключа (видна в списке ключей в профиле)."""
    try:
        key.last_used_at = _now()
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


# ---------------------------------------------------------------------------
# Быстрый расход
# ---------------------------------------------------------------------------


def resolve_ledger(db: Session, user: User, kind: str, household_id: int | None) -> LedgerAccess:
    """Книга для быстрого расхода: личная или семейная.

    Примеры: kind="personal" → личная книга; kind="household" и одна семья → её книга;
    kind="household", household_id=2 → книга семьи 2.
    Ошибки: QuickLedgerNotFoundError (книга не включена), QuickHouseholdChoiceError (семей несколько, id не указан).
    """
    ledgers = [item for item in list_ledgers(db, user) if item["kind"] == kind]
    if kind == "household" and household_id is not None:
        ledgers = [item for item in ledgers if item["household_id"] == household_id]
    if not ledgers:
        raise QuickLedgerNotFoundError
    if len(ledgers) > 1:
        raise QuickHouseholdChoiceError
    return get_ledger_access(db, ledgers[0]["id"], user)


def expense_categories(db: Session, access: LedgerAccess) -> list[FinanceCategory]:
    """Категории расходов книги по названию. Пример: [Продукты(id=1), Транспорт(id=3), ...]."""
    return list(
        db.scalars(
            select(FinanceCategory)
            .where(FinanceCategory.ledger_id == access.ledger.id, FinanceCategory.kind == "expense")
            .order_by(FinanceCategory.name)
        ).all()
    )


def resolve_category(db: Session, access: LedgerAccess, wanted: int | str | None) -> tuple[FinanceCategory, bool]:
    """Категория расхода по id или названию; не нашли — «Без категории» (её создаём, если ещё нет).

    Возвращает (категория, найдена ли запрошенная). Примеры:
      3 или "3"      → (Продукты, True), если у книги есть категория расходов с id 3;
      "продукты"     → (Продукты, True): название без учёта регистра и пробелов по краям;
      "Кофе" или None → (Без категории, False).
    Создание «Без категории» идёт без commit, в транзакции самого расхода.
    """
    categories = expense_categories(db, access)
    if wanted is not None:
        text = str(wanted).strip()
        for category in categories:
            if text.isdigit() and category.id == int(text):
                return category, True
        for category in categories:
            if category.name.casefold() == text.casefold():
                return category, True

    fallback = next((c for c in categories if c.name.casefold() == NO_CATEGORY_NAME.casefold()), None)
    if fallback is None:
        fallback = FinanceCategory(ledger_id=access.ledger.id, name=NO_CATEGORY_NAME, kind="expense")
        db.add(fallback)
        db.flush()
    # Без категории в запросе «найдено» не о чем говорить: считаем, что всё в порядке
    return fallback, wanted is None


def _cleanup_idempotency(db: Session, key: PersonalAccessKey) -> None:
    """Удаляет запомненные запросы ключа старше окна повтора (без commit)."""
    db.execute(
        delete(QuickAddRequest).where(
            QuickAddRequest.access_key_id == key.id,
            QuickAddRequest.created_at < _now() - timedelta(minutes=QUICK_IDEMPOTENCY_MINUTES),
        )
    )


def _find_repeat(db: Session, key: PersonalAccessKey, idempotency_key: str) -> QuickAddRequest | None:
    """Запомненный запрос с тем же Idempotency-Key не старше окна повтора, или None."""
    return db.scalar(
        select(QuickAddRequest).where(
            QuickAddRequest.access_key_id == key.id,
            QuickAddRequest.idempotency_key == idempotency_key,
            QuickAddRequest.created_at >= _now() - timedelta(minutes=QUICK_IDEMPOTENCY_MINUTES),
        )
    )


def _ledger_kind(access: LedgerAccess) -> str:
    return "personal" if access.ledger.user_id is not None else "household"


def _answer(db: Session, access: LedgerAccess, transaction, category: FinanceCategory, found: bool,
            today: date, duplicate: bool) -> dict:
    """Ответ быстрой команде (QuickExpenseResponse): расход и новые «Баланс», «Свободно», «В день».

    Цифры — из spending_plan, того же расчёта, что на главной и во «Финансы → Обзор».
    Пример message: "Записано 350 ₽, «Продукты». Баланс 12 000 ₽, свободно 8 000 ₽ до 5 ноя, в день 1 142,86 ₽."
    """
    currency = access.ledger.currency
    sync_recurring(db, access.ledger.id, today)
    plan = spending_plan(db, access, today)

    parts = [f"Баланс {money(plan['balance'], currency)}"]
    if plan["free"] is not None and plan["next_income_on"] is not None:
        parts.append(f"свободно {money(plan['free'], currency)} до {short_date(plan['next_income_on'])}")
    if plan["daily_allowance"] is not None:
        parts.append(f"в день {money(plan['daily_allowance'], currency)}")
    elif plan["note"]:
        parts.append(plan["note"])
    head = "Уже записано" if duplicate else "Записано"
    message = f"{head} {money(transaction.amount, currency)}, «{category.name}». " + ", ".join(parts) + "."
    if not found:
        message += " Категория не найдена — расход в «Без категории»."

    return {
        "ok": True,
        "duplicate": duplicate,
        "transaction_id": transaction.id,
        "ledger": _ledger_kind(access),
        "amount": transaction.amount,
        "currency": currency,
        "category": category.name,
        "category_found": found,
        "occurred_on": transaction.occurred_on,
        "balance": plan["balance"],
        "free": plan["free"],
        "free_until": plan["next_income_on"],
        "daily_allowance": plan["daily_allowance"],
        "message": message,
    }


def _repeat_answer(db: Session, user: User, repeat: QuickAddRequest, today: date) -> dict:
    """Ответ на повтор: прежний расход и текущие цифры его книги (новый расход не создаётся)."""
    transaction = db.get(FinanceTransaction, repeat.transaction_id)
    access = get_ledger_access(db, transaction.ledger_id, user)
    category = db.get(FinanceCategory, transaction.category_id)
    return _answer(db, access, transaction, category, True, today, duplicate=True)


def quick_expense(
    db: Session,
    key: PersonalAccessKey,
    user: User,
    data: QuickExpenseCreate,
    today: date,
    idempotency_key: str | None,
) -> dict:
    """Записывает быстрый расход и возвращает короткий ответ с новым балансом (QuickExpenseResponse).

    Путь данных: iPhone → POST /api/quick/expense {"amount": 350, "category": "Продукты"}
      → quick_routes (ключ, лимиты) → quick_expense → add_transaction (та же функция, что у формы) → commit.
    Шаги:
      1. сумма > 0, иначе QuickAmountError (422 «Сумма должна быть больше нуля»);
      2. с Idempotency-Key: тот же ключ и значение за последние 10 минут → прежний расход, duplicate=true;
      3. книга (личная/семейная), категория (или «Без категории»), дата (по умолчанию сегодня по поясу профиля);
      4. расход и отметка Idempotency-Key сохраняются одной транзакцией. Если параллельный повтор успел первым,
         база отклонит вторую отметку (уникальность), расход откатится, а ответ будет как на повтор.
    """
    if data.amount <= 0:
        raise QuickAmountError

    if idempotency_key:
        _cleanup_idempotency(db, key)
        repeat = _find_repeat(db, key, idempotency_key)
        if repeat is not None:
            db.commit()  # фиксируем уборку старых отметок
            return _repeat_answer(db, user, repeat, today)

    access = resolve_ledger(db, user, data.ledger, data.household_id)
    try:
        category, found = resolve_category(db, access, data.category)
        transaction, category = add_transaction(
            db,
            access,
            user,
            FinanceTransactionCreate(
                category_id=category.id,
                amount=data.amount,
                occurred_on=data.occurred_on or today,
                description=data.comment,
            ),
            today,
        )
        if idempotency_key:
            db.add(QuickAddRequest(access_key_id=key.id, idempotency_key=idempotency_key, transaction_id=transaction.id))
        db.commit()
        db.refresh(transaction)
    except IntegrityError:
        db.rollback()
        # Одновременный повтор с тем же Idempotency-Key уже записал расход — отвечаем как на повтор
        repeat = _find_repeat(db, key, idempotency_key) if idempotency_key else None
        if repeat is None:
            raise
        return _repeat_answer(db, user, repeat, today)
    except SQLAlchemyError:
        db.rollback()
        raise

    return _answer(db, access, transaction, category, found, today, duplicate=False)


def quick_categories(db: Session, user: User, kind: str, household_id: int | None) -> dict:
    """Категории расходов книги для меню быстрой команды (QuickCategoriesResponse). Только чтение.

    Пример: {"ledger": "personal", "names": ["Другое", "Продукты", ...], "categories": [{"id": 1, "name": "Продукты"}, ...]}
    """
    access = resolve_ledger(db, user, kind, household_id)
    categories = expense_categories(db, access)
    return {
        "ledger": _ledger_kind(access),
        "names": [category.name for category in categories],
        "categories": [{"id": category.id, "name": category.name} for category in categories],
    }


__all__ = [
    "MAX_ACTIVE_KEYS",
    "create_access_key",
    "find_active_key",
    "list_access_keys",
    "quick_categories",
    "quick_expense",
    "revoke_access_key",
    "touch_key",
]

