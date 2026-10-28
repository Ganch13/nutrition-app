"""Общие помощники для тестов повторяющихся операций, циклов и целей."""

from datetime import date

import pytest

from finance_routes import get_today
from main import app
from tests.helpers import new_household, register_and_login  # noqa: F401  (удобно импортировать отсюда)

PASSWORD = "very-strong-password-123"


@pytest.fixture()
def today(client):
    """Фиксирует «сегодня» для сервера. Меняется присваиванием: today["day"] = date(2026, 11, 20).

    По умолчанию 28 октября 2026. Зависимость get_today подменяется только внутри теста;
    фикстура client снимает подмену после теста.
    """
    holder = {"day": date(2026, 10, 28)}
    app.dependency_overrides[get_today] = lambda: holder["day"]
    return holder


def personal_ledger(client, user, currency: str = "RUB") -> int:
    """Создаёт личную книгу и возвращает её id."""
    response = client.post("/finance/ledgers", json={"kind": "personal", "currency": currency}, headers=user["headers"])
    assert response.status_code == 201, response.text
    return response.json()["id"]


def household_ledger(client, user, household_id: int, currency: str = "RUB") -> int:
    """Создаёт семейную книгу и возвращает её id."""
    response = client.post(
        "/finance/ledgers",
        json={"kind": "household", "household_id": household_id, "currency": currency},
        headers=user["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def add_rule(client, user, ledger_id: int, **fields):
    """Создаёт правило; возвращает ответ целиком. По умолчанию ежемесячный платёж 1000 ₽ начиная с 2026-11-01."""
    body = {
        "kind": "expense",
        "name": "Платёж",
        "amount": 1000,
        "frequency": "monthly",
        "start_on": "2026-11-01",
        **fields,
    }
    return client.post(f"/finance/ledgers/{ledger_id}/recurring", json=body, headers=user["headers"])


def make_rule(client, user, ledger_id: int, **fields) -> dict:
    """Как add_rule, но проверяет успех и возвращает данные правила."""
    response = add_rule(client, user, ledger_id, **fields)
    assert response.status_code == 201, response.text
    return response.json()


def confirm(client, user, ledger_id: int, rule_id: int, due_on: str, **body) -> dict:
    """Отвечает «да» на «Поступил ли платёж?» (или «Оплачено») и возвращает созданную операцию.

    body — фактические данные, например amount=48000, occurred_on="2026-10-26".
    """
    response = client.post(
        f"/finance/ledgers/{ledger_id}/recurring/{rule_id}/occurrences/{due_on}/confirm",
        json=body or None,
        headers=user["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()


def transactions(client, user, ledger_id: int, month: str) -> list[dict]:
    """Операции книги за месяц вида "2026-10"."""
    response = client.get(f"/finance/ledgers/{ledger_id}/transactions?month={month}", headers=user["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def cycles(client, user, ledger_id: int, **params) -> dict:
    response = client.get(f"/finance/ledgers/{ledger_id}/cycles", params=params, headers=user["headers"])
    assert response.status_code == 200, response.text
    return response.json()
