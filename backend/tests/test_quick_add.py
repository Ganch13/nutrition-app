"""Личные ключи доступа и быстрое добавление расхода с iPhone (ТЗ 29.10.26(2), часть 2)."""

import hashlib
import logging
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from finance_routes import get_today
from main import app
from models import PersonalAccessKey
from quick_routes import get_quick_today
from tests.finance_plan_helpers import (
    PASSWORD,
    confirm,
    household_ledger,
    make_rule,
    new_household,
    personal_ledger,
    register_and_login,
    transactions,
)


@pytest.fixture()
def today(client):
    """«Сегодня» 28 октября 2026 и для обычных эндпоинтов, и для быстрых (у них своя зависимость)."""
    day = date(2026, 10, 28)
    app.dependency_overrides[get_today] = lambda: day
    app.dependency_overrides[get_quick_today] = lambda: day
    return day


def new_key(client, user, name: str = "iPhone") -> str:
    """Создаёт личный ключ и возвращает его целиком: "lad_..."."""
    response = client.post("/access-keys", json={"name": name}, headers=user["headers"])
    assert response.status_code == 201, response.text
    return response.json()["key"]


def bearer(key: str, **extra) -> dict:
    return {"Authorization": f"Bearer {key}", **extra}


def quick(client, key: str, body: dict, **headers):
    return client.post("/quick/expense", json=body, headers=bearer(key, **headers))


def balance(client, user, ledger: int) -> Decimal:
    response = client.get(f"/finance/ledgers/{ledger}/balance", headers=user["headers"])
    assert response.status_code == 200, response.text
    return Decimal(response.json()["total"])


def with_money(client, user, ledger: int, amount: int = 20000) -> None:
    """Зарплата 25 октября подтверждена, следующая 25 ноября: в книге есть деньги и следующий доход."""
    rule = make_rule(client, user, ledger, kind="income", name="Зарплата", amount=amount, start_on="2026-10-25")
    confirm(client, user, ledger, rule["id"], "2026-10-25")


# ------------------------------------------------------------- управление ключами


def test_key_is_shown_once_and_only_hash_is_stored(client, engine):
    user = register_and_login(client, "keys@example.com")
    response = client.post("/access-keys", json={"name": "  iPhone  "}, headers=user["headers"])
    assert response.status_code == 201, response.text
    created = response.json()
    key = created["key"]

    assert key.startswith("lad_") and len(key) >= 4 + 43  # 32 случайных байта
    assert created["name"] == "iPhone"
    assert created["key_prefix"] == key[:10] and created["active"] is True
    assert created["last_used_at"] is None and created["revoked_at"] is None

    listed = client.get("/access-keys", headers=user["headers"]).json()
    assert len(listed) == 1 and "key" not in listed[0]
    assert listed[0]["key_prefix"] == key[:10]

    # В базе только SHA-256, самого ключа нет
    with sessionmaker(bind=engine)() as db:
        row = db.scalar(select(PersonalAccessKey))
        assert row.key_hash == hashlib.sha256(key.encode()).hexdigest()
        assert key not in (row.key_hash, row.key_prefix, row.name)


def test_active_keys_are_limited_to_five(client):
    user = register_and_login(client, "limit-keys@example.com")
    for number in range(5):
        new_key(client, user, f"Ключ {number}")
    response = client.post("/access-keys", json={"name": "Шестой"}, headers=user["headers"])
    assert response.status_code == 409
    assert "5" in response.json()["detail"]

    # Отозванный не считается: после отзыва можно создать новый
    first = client.get("/access-keys", headers=user["headers"]).json()[0]
    assert client.delete(f"/access-keys/{first['id']}", headers=user["headers"]).status_code == 200
    assert client.post("/access-keys", json={"name": "Шестой"}, headers=user["headers"]).status_code == 201


def test_cannot_revoke_someone_elses_key(client):
    owner = register_and_login(client, "owner-key@example.com")
    stranger = register_and_login(client, "stranger-key@example.com")
    new_key(client, owner)
    key_id = client.get("/access-keys", headers=owner["headers"]).json()[0]["id"]
    assert client.delete(f"/access-keys/{key_id}", headers=stranger["headers"]).status_code == 404
    assert client.get("/access-keys", headers=stranger["headers"]).json() == []


def test_empty_key_name_is_rejected(client):
    user = register_and_login(client, "noname@example.com")
    assert client.post("/access-keys", json={"name": "   "}, headers=user["headers"]).status_code == 422


# ------------------------------------------------------------- быстрый расход


def test_quick_expense_changes_balance_like_a_manual_one(client, today):
    user = register_and_login(client, "quick@example.com")
    ledger = personal_ledger(client, user)
    with_money(client, user, ledger)
    key = new_key(client, user)
    before = balance(client, user, ledger)  # 20 000

    response = quick(client, key, {"amount": 350, "category": "продукты", "comment": "Пятёрочка"})
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["ok"] is True and data["duplicate"] is False
    assert data["ledger"] == "personal" and data["category"] == "Продукты" and data["category_found"] is True
    assert Decimal(data["amount"]) == Decimal("350")
    assert data["occurred_on"] == "2026-10-28"  # по умолчанию «сегодня»
    # Баланс уменьшился на сумму расхода — как при обычной форме
    assert Decimal(data["balance"]) == before - 350 == balance(client, user, ledger)
    # «Свободно» и «в день» — те же цифры, что на главной
    home = next(item for item in client.get("/finance/home", headers=user["headers"]).json() if item["ledger_id"] == ledger)
    assert Decimal(data["free"]) == Decimal(home["free"])
    assert data["free_until"] == home["free_until"] == "2026-11-25"
    assert Decimal(data["daily_allowance"]) == (Decimal(home["free"]) / 28).quantize(Decimal("0.01"))
    assert "Записано 350" in data["message"] and "«Продукты»" in data["message"]

    # Операция видна в «Операциях» как обычная: автор — владелец ключа, описание — комментарий
    operation = next(item for item in transactions(client, user, ledger, "2026-10") if item["id"] == data["transaction_id"])
    assert operation["kind"] == "expense" and operation["description"] == "Пятёрочка"
    assert operation["created_by_user_id"] == user["id"]


def test_quick_expense_category_by_id_comma_amount_and_date(client, today):
    user = register_and_login(client, "quick-id@example.com")
    ledger = personal_ledger(client, user)
    key = new_key(client, user)
    categories = client.get("/quick/categories", headers=bearer(key)).json()
    transport = next(item for item in categories["categories"] if item["name"] == "Транспорт")

    response = quick(client, key, {"amount": "1 250,50", "category": transport["id"], "date": "2026-10-27"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["category"] == "Транспорт" and Decimal(data["amount"]) == Decimal("1250.50")
    assert data["occurred_on"] == "2026-10-27"


def test_unknown_category_goes_to_no_category(client, today):
    user = register_and_login(client, "nocat@example.com")
    ledger = personal_ledger(client, user)
    key = new_key(client, user)

    first = quick(client, key, {"amount": 100, "category": "Кофе на вынос"}).json()
    assert first["category"] == "Без категории" and first["category_found"] is False
    assert "Категория не найдена" in first["message"]
    # Без категории в запросе — тоже «Без категории», вторая такая же категория не создаётся
    second = quick(client, key, {"amount": 50}).json()
    assert second["category"] == "Без категории" and second["category_found"] is True
    names = [item["name"] for item in client.get(f"/finance/ledgers/{ledger}/categories", headers=user["headers"]).json()]
    assert names.count("Без категории") == 1


def test_zero_or_negative_amount_gives_clear_error(client, today):
    user = register_and_login(client, "zero@example.com")
    personal_ledger(client, user)
    key = new_key(client, user)
    for amount in (0, -5, "0,00"):
        response = quick(client, key, {"amount": amount})
        assert response.status_code == 422, response.text
        assert response.json()["detail"] == "Сумма должна быть больше нуля"
    # Суммы нет совсем — тоже 422 (стандартная ошибка проверки)
    assert quick(client, key, {}).status_code == 422


def test_household_ledger_and_missing_ledger(client, today):
    owner = register_and_login(client, "quick-home@example.com")
    member = register_and_login(client, "quick-member@example.com")
    household = new_household(client, owner, member)
    key = new_key(client, member)

    # Семейные финансы ещё не включены
    response = quick(client, key, {"amount": 100, "ledger": "household"})
    assert response.status_code == 404
    # Личные тоже не включены
    assert quick(client, key, {"amount": 100}).status_code == 404

    family = household_ledger(client, owner, household)
    response = quick(client, key, {"amount": 700, "category": "Продукты", "ledger": "household"})
    assert response.status_code == 200, response.text
    assert response.json()["ledger"] == "household"
    assert balance(client, owner, family) == Decimal("-700")
    names = client.get("/quick/categories?ledger=household", headers=bearer(key)).json()["names"]
    assert "Продукты" in names


# ------------------------------------------------------------- защита


def test_revoked_wrong_and_missing_key_give_401(client, today):
    user = register_and_login(client, "revoke@example.com")
    personal_ledger(client, user)
    key = new_key(client, user)
    assert quick(client, key, {"amount": 10}).status_code == 200

    key_id = client.get("/access-keys", headers=user["headers"]).json()[0]["id"]
    revoked = client.delete(f"/access-keys/{key_id}", headers=user["headers"])
    assert revoked.status_code == 200 and revoked.json()["active"] is False
    # Отозванный ключ перестаёт работать сразу
    assert quick(client, key, {"amount": 10}).status_code == 401
    assert client.get("/quick/categories", headers=bearer(key)).status_code == 401

    assert quick(client, "lad_" + "x" * 43, {"amount": 10}).status_code == 401
    assert quick(client, "not-a-key", {"amount": 10}).status_code == 401
    assert client.post("/quick/expense", json={"amount": 10}).status_code == 401
    # Обычный токен входа на быстрых эндпоинтах не работает: только ключ
    assert client.post("/quick/expense", json={"amount": 10}, headers=user["headers"]).status_code == 401


def test_key_does_not_work_on_other_endpoints(client, today):
    user = register_and_login(client, "scope@example.com")
    ledger = personal_ledger(client, user)
    key = new_key(client, user)
    for method, path in [
        ("get", "/users/me"),
        ("get", f"/users/{user['id']}"),
        ("get", "/finance/ledgers"),
        ("get", f"/finance/ledgers/{ledger}/balance"),
        ("get", "/finance/home"),
        ("get", "/access-keys"),
        ("post", "/access-keys"),
    ]:
        response = getattr(client, method)(path, headers=bearer(key), **({"json": {"name": "x"}} if method == "post" else {}))
        assert response.status_code == 401, (path, response.status_code)


def test_same_idempotency_key_does_not_create_duplicate(client, today):
    user = register_and_login(client, "idem@example.com")
    ledger = personal_ledger(client, user)
    key = new_key(client, user)

    first = quick(client, key, {"amount": 300}, **{"Idempotency-Key": "abc-123"})
    again = quick(client, key, {"amount": 300}, **{"Idempotency-Key": "abc-123"})
    assert first.status_code == again.status_code == 200
    assert again.json()["duplicate"] is True and "Уже записано" in again.json()["message"]
    assert again.json()["transaction_id"] == first.json()["transaction_id"]
    assert balance(client, user, ledger) == Decimal("-300")

    # Другое значение — это уже другой расход
    other = quick(client, key, {"amount": 300}, **{"Idempotency-Key": "abc-124"})
    assert other.json()["duplicate"] is False
    # Без заголовка каждый запрос — новый расход
    quick(client, key, {"amount": 300})
    assert len(transactions(client, user, ledger, "2026-10")) == 3


def test_idempotency_window_is_ten_minutes(client, today, engine):
    user = register_and_login(client, "idem-window@example.com")
    ledger = personal_ledger(client, user)
    key = new_key(client, user)
    quick(client, key, {"amount": 100}, **{"Idempotency-Key": "late"})

    # Сдвигаем отметку на 11 минут назад: повтор после окна создаёт новый расход
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text("UPDATE quick_add_requests SET created_at = created_at - interval '11 minutes'"))
    again = quick(client, key, {"amount": 100}, **{"Idempotency-Key": "late"})
    assert again.json()["duplicate"] is False
    assert len(transactions(client, user, ledger, "2026-10")) == 2


def test_rate_limit_per_key_gives_429(client, today):
    user = register_and_login(client, "rate@example.com")
    personal_ledger(client, user)
    key = new_key(client, user)
    for _ in range(30):
        assert client.get("/quick/categories", headers=bearer(key)).status_code == 200
    response = quick(client, key, {"amount": 10})
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_rate_limit_per_address_counts_wrong_keys(client, today):
    for _ in range(60):
        assert quick(client, "lad_wrong", {"amount": 10}).status_code == 401
    assert quick(client, "lad_wrong", {"amount": 10}).status_code == 429


def test_last_used_is_updated_and_key_is_not_logged(client, today, caplog):
    user = register_and_login(client, "used@example.com")
    personal_ledger(client, user)
    key = new_key(client, user)
    assert client.get("/access-keys", headers=user["headers"]).json()[0]["last_used_at"] is None

    with caplog.at_level(logging.INFO):
        assert quick(client, key, {"amount": 10}).status_code == 200
    assert client.get("/access-keys", headers=user["headers"]).json()[0]["last_used_at"] is not None
    # В журнал попадает только начало ключа
    assert key not in caplog.text
    assert key[:10] in caplog.text


def test_password_change_revokes_keys(client, today):
    user = register_and_login(client, "pwd-keys@example.com")
    personal_ledger(client, user)
    key = new_key(client, user)
    assert quick(client, key, {"amount": 10}).status_code == 200

    changed = client.post(
        "/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "совсем-новый-пароль-456"},
        headers=user["headers"],
    )
    assert changed.status_code == 200, changed.text
    assert quick(client, key, {"amount": 10}).status_code == 401

    headers = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    listed = client.get("/access-keys", headers=headers).json()
    assert listed[0]["active"] is False


def test_account_deletion_removes_keys(client, today):
    user = register_and_login(client, "gone-keys@example.com")
    personal_ledger(client, user)
    key = new_key(client, user)
    deleted = client.post("/auth/delete-account", json={"password": PASSWORD}, headers=user["headers"])
    assert deleted.status_code == 204, deleted.text
    assert quick(client, key, {"amount": 10}).status_code == 401
