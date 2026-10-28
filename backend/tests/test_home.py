"""Главная страница: деньги по личной и семейной книге, скрытые блоки."""

from decimal import Decimal

from tests.finance_plan_helpers import (  # noqa: F401  (today — фикстура)
    confirm,
    household_ledger,
    make_rule,
    new_household,
    personal_ledger,
    register_and_login,
    today,
)


def dec(value) -> Decimal:
    return Decimal(str(value))


def spend(client, user, ledger_id: int, amount: int, occurred_on: str, category: str = "Продукты") -> None:
    """Добавляет обычную трату в книгу."""
    categories = client.get(f"/finance/ledgers/{ledger_id}/categories", headers=user["headers"]).json()
    category_id = next(c["id"] for c in categories if c["name"] == category)
    response = client.post(
        f"/finance/ledgers/{ledger_id}/transactions",
        json={"category_id": category_id, "amount": amount, "occurred_on": occurred_on},
        headers=user["headers"],
    )
    assert response.status_code == 201, response.text


def home(client, user) -> list[dict]:
    response = client.get("/finance/home", headers=user["headers"])
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------- деньги


def test_home_money_without_ledgers_is_empty(client, today):
    user = register_and_login(client, "nomoney@example.com")
    assert home(client, user) == []


def test_personal_and_family_money_are_separate(client, today):
    owner = register_and_login(client, "home-owner@example.com")
    wife = register_and_login(client, "home-wife@example.com")
    household_id = new_household(client, owner, wife)
    personal = personal_ledger(client, owner)
    family = household_ledger(client, owner, household_id)

    # Личная книга: зарплата 25-го получена, аренда 3 ноября ещё впереди, потрачено 4 000
    salary = make_rule(client, owner, personal, kind="income", name="Зарплата", amount=90000, start_on="2026-10-25")
    make_rule(client, owner, personal, name="Аренда", amount=35000, start_on="2026-11-03")
    confirm(client, owner, personal, salary["id"], "2026-10-25")
    spend(client, owner, personal, 4000, "2026-10-27")
    # Будущая трата в «сколько всего» не входит
    spend(client, owner, personal, 1000, "2026-10-30")
    client.patch(f"/finance/ledgers/{personal}", json={"cycle_mode": "income"}, headers=owner["headers"])

    # Семейная книга: только траты жены
    spend(client, wife, family, 2500, "2026-10-20")

    items = home(client, owner)
    assert [item["kind"] for item in items] == ["personal", "household"]
    mine, ours = items

    assert mine["ledger_id"] == personal and mine["currency"] == "RUB"
    assert dec(mine["total"]) == Decimal("86000")  # 90 000 − 4 000
    assert (mine["period_start"], mine["period_end"]) == ("2026-10-25", "2026-11-24")
    # Свободно в периоде: доход 90 000 − аренда 35 000 − траты 5 000
    assert dec(mine["free"]) == Decimal("50000")

    # Личные деньги в семейный разрез не входят
    assert ours["ledger_id"] == family and ours["household_name"] == "Дом"
    assert dec(ours["total"]) == Decimal("-2500")
    assert (ours["period_start"], ours["period_end"]) == ("2026-10-01", "2026-10-31")

    # Жена видит только семейную книгу: личной у неё нет, а чужая личная недоступна
    assert [item["ledger_id"] for item in home(client, wife)] == [family]


def test_home_money_requires_login(client):
    assert client.get("/finance/home").status_code == 401
    assert client.get("/finance/income-prompts").status_code == 401


# ---------------------------------------------------------------- скрытые блоки


def test_hidden_home_blocks_are_saved_in_profile(client):
    user = register_and_login(client, "blocks@example.com")
    url = f"/users/{user['id']}"
    assert client.get("/users/me", headers=user["headers"]).json()["home_hidden_blocks"] == []

    response = client.patch(url, json={"home_hidden_blocks": ["weight", "money", "weight"]}, headers=user["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["home_hidden_blocks"] == ["money", "weight"]
    assert client.get("/users/me", headers=user["headers"]).json()["home_hidden_blocks"] == ["money", "weight"]

    # Вернуть все блоки — пустой список; null и неизвестные блоки не принимаются
    assert client.patch(url, json={"home_hidden_blocks": []}, headers=user["headers"]).json()["home_hidden_blocks"] == []
    assert client.patch(url, json={"home_hidden_blocks": None}, headers=user["headers"]).status_code == 422
    assert client.patch(url, json={"home_hidden_blocks": ["fridge"]}, headers=user["headers"]).status_code == 422
