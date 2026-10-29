"""Главная страница: деньги по личной и семейной книге, скрытые блоки."""

from datetime import date
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
    # Свободно: баланс 86 000 − аренда 35 000 до следующей зарплаты 25 ноября
    # (будущая трата 30 октября ещё не случилась и в баланс не входит)
    assert dec(mine["free"]) == Decimal("51000")
    assert mine["free_until"] == "2026-11-25" and mine["spending_status"] == "ok"

    # Личные деньги в семейный разрез не входят
    assert ours["ledger_id"] == family and ours["household_name"] == "Дом"
    assert dec(ours["total"]) == Decimal("-2500")
    assert (ours["period_start"], ours["period_end"]) == ("2026-10-01", "2026-10-31")

    # Жена видит только семейную книгу: личной у неё нет, а чужая личная недоступна
    assert [item["ledger_id"] for item in home(client, wife)] == [family]


def test_total_counts_only_actual_operations(client, today):
    """«Всего» — кошелёк: запланированные доходы и платежи цифру не меняют, подтверждённые меняют.

    Сегодня 28 октября. Проверяем личную и семейную книги одинаково.
    """
    owner = register_and_login(client, "fact-owner@example.com")
    household_id = new_household(client, owner)
    for ledger in (personal_ledger(client, owner), household_ledger(client, owner, household_id)):
        def total() -> Decimal:
            item = next(i for i in home(client, owner) if i["ledger_id"] == ledger)
            return dec(item["total"])

        spend(client, owner, ledger, 1000, "2026-10-20")
        assert total() == Decimal("-1000")

        # Запланированные: зарплата 25-го (уже прошла, но не подтверждена), аренда без автосписания 3-го
        # (уже прошла, но не оплачена), будущая зарплата 10 ноября — ничего из этого не входит
        salary = make_rule(client, owner, ledger, kind="income", name="Зарплата", amount=90000, start_on="2026-10-25")
        rent = make_rule(client, owner, ledger, name="Аренда", amount=35000, start_on="2026-10-03")
        make_rule(client, owner, ledger, kind="income", name="Премия", amount=20000, start_on="2026-11-10")
        assert total() == Decimal("-1000")

        # Автосписание — факт в день платежа: подписка 15-го уже списалась, 15 ноября — ещё нет
        make_rule(client, owner, ledger, name="Подписка", amount=300, start_on="2026-10-15", auto_post=True)
        assert total() == Decimal("-1300")

        # Подтверждённые «Получено» и «Оплачено» входят
        confirm(client, owner, ledger, salary["id"], "2026-10-25")
        confirm(client, owner, ledger, rent["id"], "2026-10-03")
        assert total() == Decimal("53700")  # −1 300 + 90 000 − 35 000

        # Подтверждение заранее с будущей датой поступления не входит, пока дата не наступит
        bonus = make_rule(client, owner, ledger, kind="income", name="Бонус", amount=5000, start_on="2026-10-30")
        confirm(client, owner, ledger, bonus["id"], "2026-10-30", occurred_on="2026-10-30")
        assert total() == Decimal("53700")


def test_expected_salary_is_not_free_money(client, today):
    """Случай из ТЗ: баланс 0, зарплата 70 000 ещё не подтверждена → свободно 0 и в день 0, а не 23 333."""
    user = register_and_login(client, "plan@example.com")
    ledger = personal_ledger(client, user)

    def plan() -> dict:
        response = client.get(f"/finance/ledgers/{ledger}/cycles", params={"count": 1}, headers=user["headers"])
        return response.json()["spending"]

    def item() -> dict:
        return next(i for i in home(client, user) if i["ledger_id"] == ledger)

    # Нет основного дохода — вместо числа понятный текст
    assert plan()["status"] == "no_income" and plan()["free"] is None and plan()["daily_allowance"] is None
    assert item()["free"] is None and "Нет следующего дохода" in item()["spending_note"]

    # Зарплата 70 000 ожидается 31 октября (сегодня 28-е), не подтверждена
    salary = make_rule(client, user, ledger, kind="income", name="Зарплата", amount=70000, start_on="2026-10-31")
    p = plan()
    assert dec(p["balance"]) == 0 and dec(p["free"]) == 0
    assert (p["next_income_on"], p["days_left"]) == ("2026-10-31", 3)
    assert dec(p["daily_allowance"]) == 0
    assert dec(item()["total"]) == 0 and dec(item()["free"]) == 0 and item()["free_until"] == "2026-10-31"

    # Платёж 30-го входит, платёж в день зарплаты 31-го — уже в следующий период
    make_rule(client, user, ledger, name="Связь", amount=600, start_on="2026-10-30")
    make_rule(client, user, ledger, name="Кредит", amount=9000, start_on="2026-10-31")
    p = plan()
    assert dec(p["mandatory_due"]) == Decimal("600") and dec(p["free"]) == Decimal("-600")
    assert p["status"] == "gap" and p["daily_allowance"] is None and p["note"].startswith("Не хватает 600")

    # Зарплата сегодня (0 дней) — деления нет, просим подтвердить
    today["day"] = date(2026, 10, 31)
    p = plan()
    assert (p["days_left"], p["status"], p["daily_allowance"]) == (0, "income_today", None)
    assert "подтвердите" in p["note"]

    # После «Получено» баланс 70 000, граница переезжает на 30 ноября
    confirm(client, user, ledger, salary["id"], "2026-10-31")
    p = plan()
    assert dec(p["balance"]) == Decimal("70000") and p["next_income_on"] == "2026-11-30"
    # До 29 ноября: кредит 31 октября 9 000 (сегодня), связь 30 ноября уже в следующем периоде
    assert dec(p["mandatory_due"]) == Decimal("9000") and dec(p["free"]) == Decimal("61000")
    assert p["days_left"] == 30 and dec(p["daily_allowance"]) == (Decimal("61000") / 30).quantize(Decimal("0.01"))


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
