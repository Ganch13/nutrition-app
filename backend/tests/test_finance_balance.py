"""Баланс книги и корректировки «на счетах на самом деле столько-то» (пункт 1 ТЗ от 29.10.2026)."""

from decimal import Decimal

from tests.finance_plan_helpers import (  # noqa: F401  (today — фикстура)
    household_ledger,
    new_household,
    personal_ledger,
    register_and_login,
    today,
)
from tests.test_home import home, spend


def dec(value) -> Decimal:
    return Decimal(str(value))


def balance_url(ledger_id: int) -> str:
    return f"/finance/ledgers/{ledger_id}/balance"


def set_balance(client, user, ledger_id: int, actual, note: str | None = None):
    """POST фактического остатка; возвращает ответ целиком (код проверяет тест)."""
    body = {"actual": actual} if note is None else {"actual": actual, "note": note}
    return client.post(balance_url(ledger_id), json=body, headers=user["headers"])


def home_total(client, user, ledger_id: int) -> Decimal:
    return dec(next(i for i in home(client, user) if i["ledger_id"] == ledger_id)["total"])


def test_actual_balance_changes_total_but_not_reports(client, today):
    user = register_and_login(client, "balance@example.com")
    ledger = personal_ledger(client, user)
    spend(client, user, ledger, 4000, "2026-10-20")
    assert home_total(client, user, ledger) == Decimal("-4000")

    # «На счетах на самом деле 52 300» → корректировка +56 300
    response = set_balance(client, user, ledger, 52300, note="  сверка с банком ")
    assert response.status_code == 201, response.text
    data = response.json()
    assert dec(data["total"]) == Decimal("52300")
    assert dec(data["adjustments_total"]) == Decimal("56300")
    [adjustment] = data["adjustments"]
    assert dec(adjustment["amount"]) == Decimal("56300")
    assert adjustment["adjusted_on"] == "2026-10-28"
    assert adjustment["note"] == "сверка с банком"
    assert adjustment["created_by_name"] == "Test User"

    # На главной та же цифра
    assert home_total(client, user, ledger) == Decimal("52300")

    # Отчёт за месяц корректировку не видит: доходов нет, расход 4 000
    summary = client.get(f"/finance/ledgers/{ledger}/summary?month=2026-10", headers=user["headers"]).json()
    assert dec(summary["income"]) == 0 and dec(summary["expense"]) == Decimal("4000")

    # Следующая сверка считает разницу от уже скорректированного баланса: 50 000 → −2 300
    data = set_balance(client, user, ledger, 50000).json()
    assert dec(data["total"]) == Decimal("50000")
    assert [dec(a["amount"]) for a in data["adjustments"]] == [Decimal("-2300"), Decimal("56300")]

    # Удаление последней корректировки возвращает 52 300
    latest = data["adjustments"][0]["id"]
    response = client.delete(f"{balance_url(ledger)}/adjustments/{latest}", headers=user["headers"])
    assert response.status_code == 200, response.text
    assert dec(response.json()["total"]) == Decimal("52300")
    assert dec(client.get(balance_url(ledger), headers=user["headers"]).json()["total"]) == Decimal("52300")


def test_same_balance_is_rejected(client, today):
    user = register_and_login(client, "balance-same@example.com")
    ledger = personal_ledger(client, user)
    spend(client, user, ledger, 1500, "2026-10-20")

    response = set_balance(client, user, ledger, -1500)
    assert response.status_code == 422
    assert response.json()["detail"] == "Баланс уже совпадает с введённой суммой"

    # Отрицательный остаток допустим
    assert set_balance(client, user, ledger, -2000).status_code == 201


def test_family_balance_permissions(client, today):
    owner = register_and_login(client, "balance-owner@example.com", name="Даня")
    member = register_and_login(client, "balance-member@example.com", name="Леся")
    stranger = register_and_login(client, "balance-stranger@example.com")
    family = household_ledger(client, owner, new_household(client, owner, member))

    # Любой участник может сверить баланс семьи
    data = set_balance(client, member, family, 1000).json()
    member_adjustment = data["adjustments"][0]["id"]
    owner_adjustment = set_balance(client, owner, family, 3000).json()["adjustments"][0]["id"]
    assert home_total(client, member, family) == Decimal("3000")

    # Чужую корректировку участник удалить не может, владелец может
    response = client.delete(f"{balance_url(family)}/adjustments/{owner_adjustment}", headers=member["headers"])
    assert response.status_code == 403
    response = client.delete(f"{balance_url(family)}/adjustments/{member_adjustment}", headers=owner["headers"])
    assert response.status_code == 200
    assert dec(response.json()["total"]) == Decimal("2000")

    # Посторонний книгу не видит, корректировка чужой книги как будто не существует
    assert client.get(balance_url(family), headers=stranger["headers"]).status_code == 404
    assert set_balance(client, stranger, family, 10).status_code == 404
    own = personal_ledger(client, stranger)
    response = client.delete(f"{balance_url(own)}/adjustments/{owner_adjustment}", headers=stranger["headers"])
    assert response.status_code == 404


def test_balance_requires_login(client):
    assert client.get(balance_url(1)).status_code == 401
    assert client.post(balance_url(1), json={"actual": 1}).status_code == 401
