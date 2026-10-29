"""Бюджетные циклы, советы и оценка долговой нагрузки."""

from datetime import date
from decimal import Decimal

from tests.finance_plan_helpers import (  # noqa: F401  (today — фикстура)
    confirm,
    cycles,
    household_ledger,
    make_rule,
    new_household,
    personal_ledger,
    register_and_login,
    today,
    transactions,
)


def dec(value) -> Decimal:
    return Decimal(str(value))


def setup_two_incomes(client, user, ledger, *, rent_day=3, rent=35000):
    """Аванс 50 000 ₽ 10-го, зарплата 90 000 ₽ 25-го, аренда и кредит. Правила действуют с сентября."""
    make_rule(client, user, ledger, kind="income", name="Аванс", amount=50000, start_on="2026-09-10")
    make_rule(client, user, ledger, kind="income", name="Зарплата", amount=90000, start_on="2026-09-25")
    make_rule(client, user, ledger, name="Аренда", amount=rent, start_on=f"2026-09-{rent_day:02d}")
    make_rule(client, user, ledger, name="Кредит", amount=26000, start_on="2026-09-12")


def confirm_income(client, user, ledger, name, *due_dates):
    """Отвечает «да» на «Поступил ли платёж?» для дохода name за даты due_dates."""
    rules = client.get(f"/finance/ledgers/{ledger}/recurring", headers=user["headers"]).json()
    rule = next(r for r in rules if r["name"] == name)
    for due_on in due_dates:
        confirm(client, user, ledger, rule["id"], due_on)


def switch_mode(client, user, ledger, mode):
    return client.patch(f"/finance/ledgers/{ledger}", json={"cycle_mode": mode}, headers=user["headers"])


# ------------------------------------------------------------- режимы периода


def test_default_mode_is_calendar_month(client, today):
    user = register_and_login(client, "cal@example.com")
    ledger = personal_ledger(client, user)
    setup_two_incomes(client, user, ledger)

    data = cycles(client, user, ledger, count=2)
    assert data["mode"] == "calendar"
    first, second = data["cycles"]
    assert (first["start"], first["end"], first["is_current"]) == ("2026-10-01", "2026-10-31", True)
    assert (second["start"], second["end"]) == ("2026-11-01", "2026-11-30")
    assert first["days_total"] == 31 and first["days_left"] == 4 and second["days_left"] is None


def test_income_mode_builds_cycles_between_incomes(client, today):
    user = register_and_login(client, "inc-cycle@example.com")
    ledger = personal_ledger(client, user)
    setup_two_incomes(client, user, ledger)

    response = switch_mode(client, user, ledger, "income")
    assert response.status_code == 200 and response.json()["cycle_mode"] == "income"

    data = cycles(client, user, ledger, count=3, previous=1)
    assert data["mode"] == "income"
    assert [(c["start"], c["end"]) for c in data["cycles"]] == [
        ("2026-10-10", "2026-10-24"),
        ("2026-10-25", "2026-11-09"),
        ("2026-11-10", "2026-11-24"),
        ("2026-11-25", "2026-12-09"),
    ]
    assert [c["is_current"] for c in data["cycles"]] == [False, True, False, False]


def test_cycle_numbers_add_up(client, today):
    user = register_and_login(client, "nums@example.com")
    ledger = personal_ledger(client, user)
    setup_two_incomes(client, user, ledger)
    switch_mode(client, user, ledger, "income")

    # Пока зарплату 25 октября не подтвердили, она только ожидается (и уже просрочена)
    current = cycles(client, user, ledger, count=1)["cycles"][0]
    assert dec(current["income_received"]) == 0 and dec(current["income_expected"]) == Decimal("90000")
    confirm_income(client, user, ledger, "Зарплата", "2026-10-25")

    # Обычная трата в текущем периоде
    categories = client.get(f"/finance/ledgers/{ledger}/categories", headers=user["headers"]).json()
    groceries = next(c["id"] for c in categories if c["name"] == "Продукты")
    client.post(
        f"/finance/ledgers/{ledger}/transactions",
        json={"category_id": groceries, "amount": 4000, "occurred_on": "2026-10-27"},
        headers=user["headers"],
    )

    report = cycles(client, user, ledger, count=1)
    current = report["cycles"][0]
    assert (current["start"], current["end"]) == ("2026-10-25", "2026-11-09")
    # В этом периоде зарплата 25 октября уже получена, аванс 10 ноября придёт уже в следующем
    assert dec(current["income_received"]) == Decimal("90000")
    assert dec(current["income_expected"]) == 0
    assert dec(current["income_total"]) == Decimal("90000")
    # Аренда 3 ноября ещё не оплачена
    assert dec(current["mandatory_pending"]) == Decimal("35000")
    assert dec(current["mandatory_total"]) == Decimal("35000")
    assert dec(current["free_after_mandatory"]) == Decimal("55000")
    assert dec(current["other_spent"]) == Decimal("4000")
    assert dec(current["available"]) == Decimal("51000")
    # До 9 ноября включительно с сегодняшним днём: 28, 29, 30, 31 октября и 1–9 ноября = 13 дней
    assert current["days_left"] == 13
    # «Можно тратить в день» — из общего расчёта: баланс 86 000 − аренда 35 000 = 51 000 на 13 дней до аванса
    spending = report["spending"]
    assert dec(spending["balance"]) == Decimal("86000")
    assert dec(spending["mandatory_due"]) == Decimal("35000")
    assert dec(spending["free"]) == Decimal("51000")
    assert (spending["next_income_on"], spending["days_left"]) == ("2026-11-10", 13)
    assert dec(spending["daily_allowance"]) == (Decimal("51000") / 13).quantize(Decimal("0.01"))
    assert spending["status"] == "ok"
    assert current["mandatory_share"] == round(35000 / 90000, 4)
    assert current["status"] == "ok"
    kinds = {(item["rule_name"], item["status"]) for item in current["items"]}
    assert ("Зарплата", "posted") in kinds and ("Аренда", "pending") in kinds


def test_paid_mandatory_payment_moves_from_pending_to_paid(client, today):
    user = register_and_login(client, "paid@example.com")
    ledger = personal_ledger(client, user)
    setup_two_incomes(client, user, ledger)
    switch_mode(client, user, ledger, "income")

    rules = client.get(f"/finance/ledgers/{ledger}/recurring", headers=user["headers"]).json()
    rent = next(r for r in rules if r["name"] == "Аренда")
    today["day"] = date(2026, 11, 3)
    paid = client.post(
        f"/finance/ledgers/{ledger}/recurring/{rent['id']}/occurrences/2026-11-03/confirm",
        json={"amount": 34000},
        headers=user["headers"],
    )
    assert paid.status_code == 201

    current = cycles(client, user, ledger, count=1)["cycles"][0]
    assert dec(current["mandatory_paid"]) == Decimal("34000")
    assert dec(current["mandatory_pending"]) == 0
    # Оплата не попадает в «обычные траты», хотя это тоже расход в журнале
    assert dec(current["other_spent"]) == 0


def test_skipped_payment_is_excluded(client, today):
    user = register_and_login(client, "skipc@example.com")
    ledger = personal_ledger(client, user)
    setup_two_incomes(client, user, ledger)
    switch_mode(client, user, ledger, "income")
    rules = client.get(f"/finance/ledgers/{ledger}/recurring", headers=user["headers"]).json()
    rent = next(r for r in rules if r["name"] == "Аренда")
    client.post(f"/finance/ledgers/{ledger}/recurring/{rent['id']}/occurrences/2026-11-03/skip", headers=user["headers"])

    current = cycles(client, user, ledger, count=1)["cycles"][0]
    assert dec(current["mandatory_total"]) == 0
    assert all(item["rule_name"] != "Аренда" for item in current["items"])


# ------------------------------------------------------------- кассовый разрыв и советы


def test_cash_gap_is_detected_and_advice_suggests_moving_a_payment(client, today):
    user = register_and_login(client, "gap@example.com")
    ledger = personal_ledger(client, user)
    # Аренда 65 000 ₽ 15-го числа попадает в «авансовый» период: доход 50 000 ₽, платежи 91 000 ₽
    setup_two_incomes(client, user, ledger, rent_day=15, rent=65000)
    switch_mode(client, user, ledger, "income")

    data = cycles(client, user, ledger, count=3)
    current, advance_cycle, third = data["cycles"]
    assert (advance_cycle["start"], advance_cycle["end"]) == ("2026-11-10", "2026-11-24")
    assert advance_cycle["status"] == "gap"
    assert dec(advance_cycle["income_total"]) == Decimal("50000")
    assert dec(advance_cycle["mandatory_total"]) == Decimal("91000")
    assert dec(advance_cycle["free_after_mandatory"]) == Decimal("-41000")
    assert current["status"] == "ok" and third["status"] == "ok"

    gap = next(item for item in data["advice"] if item["code"] == "cash_gap")
    assert gap["severity"] == "danger"
    assert "Не хватает 41" in gap["text"]
    assert "«Аренда»" in gap["text"] and "денег хватит" in gap["text"]
    # Нагрузка по периодам неравномерна: в текущем платежей нет, в авансовом 182 % дохода
    assert any(item["code"] == "unbalanced" for item in data["advice"])


def test_no_cash_gap_advice_when_everything_fits(client, today):
    user = register_and_login(client, "fits@example.com")
    ledger = personal_ledger(client, user)
    setup_two_incomes(client, user, ledger)
    switch_mode(client, user, ledger, "income")
    advice = cycles(client, user, ledger, count=3)["advice"]
    assert all(item["code"] != "cash_gap" for item in advice)
    # Пока зарплата не подтверждена, денег на счетах нет — совета «сколько в день» тоже нет
    assert all(item["code"] != "daily_allowance" for item in advice)
    confirm_income(client, user, ledger, "Зарплата", "2026-10-25")
    advice = cycles(client, user, ledger, count=3)["advice"]
    assert any(item["code"] == "daily_allowance" for item in advice)


def test_overdue_payment_advice(client, today):
    user = register_and_login(client, "over@example.com")
    ledger = personal_ledger(client, user)
    make_rule(client, user, ledger, name="Телефон", amount=700, start_on="2026-10-20")
    data = cycles(client, user, ledger, count=1)
    overdue = next(item for item in data["advice"] if item["code"] == "overdue")
    assert "«Телефон»" in overdue["text"] and "20 окт" in overdue["text"]


def test_suggest_income_cycle_when_two_incomes_in_calendar_mode(client, today):
    user = register_and_login(client, "suggest@example.com")
    ledger = personal_ledger(client, user)
    setup_two_incomes(client, user, ledger)
    codes = {item["code"] for item in cycles(client, user, ledger)["advice"]}
    assert "suggest_income_cycle" in codes
    switch_mode(client, user, ledger, "income")
    codes = {item["code"] for item in cycles(client, user, ledger)["advice"]}
    assert "suggest_income_cycle" not in codes


def test_income_mode_without_incomes_warns_and_falls_back_to_month(client, today):
    user = register_and_login(client, "empty@example.com")
    ledger = personal_ledger(client, user)
    switch_mode(client, user, ledger, "income")
    data = cycles(client, user, ledger, count=1)
    assert (data["cycles"][0]["start"], data["cycles"][0]["end"]) == ("2026-10-01", "2026-10-31")
    assert any(item["code"] == "income_cycle_without_income" for item in data["advice"])


def test_cycles_parameters_are_validated(client, today):
    user = register_and_login(client, "params@example.com")
    ledger = personal_ledger(client, user)
    base = f"/finance/ledgers/{ledger}/cycles"
    assert client.get(base, params={"count": 0}, headers=user["headers"]).status_code == 422
    assert client.get(base, params={"count": 13}, headers=user["headers"]).status_code == 422
    assert client.get(base, params={"previous": -1}, headers=user["headers"]).status_code == 422


def test_paused_rule_keeps_history_in_past_cycle(client, today):
    user = register_and_login(client, "pause@example.com")
    ledger = personal_ledger(client, user)
    rule = make_rule(client, user, ledger, kind="income", name="Подработка", amount=10000, start_on="2026-10-05")
    # Получена 5 октября; ставим правило на паузу
    confirm(client, user, ledger, rule["id"], "2026-10-05")
    client.patch(f"/finance/ledgers/{ledger}/recurring/{rule['id']}", json={"is_active": False}, headers=user["headers"])
    current = cycles(client, user, ledger, count=1)["cycles"][0]
    assert dec(current["income_received"]) == Decimal("10000")
    assert dec(current["income_expected"]) == 0


def test_additional_income_counts_in_period_but_sets_no_boundary(client, today):
    user = register_and_login(client, "extra@example.com")
    ledger = personal_ledger(client, user)
    setup_two_incomes(client, user, ledger)
    # Дополнительный доход 1-го числа: в сумму периода входит, нового периода не начинает
    make_rule(client, user, ledger, kind="income", name="Кэшбэк", amount=700, start_on="2026-09-01", is_primary=False)
    switch_mode(client, user, ledger, "income")

    data = cycles(client, user, ledger, count=2)
    assert [(c["start"], c["end"]) for c in data["cycles"]] == [
        ("2026-10-25", "2026-11-09"),
        ("2026-11-10", "2026-11-24"),
    ]
    current = data["cycles"][0]
    assert dec(current["income_total"]) == Decimal("90700")
    cashback = next(item for item in current["items"] if item["rule_name"] == "Кэшбэк")
    assert cashback["due_on"] == "2026-11-01" and cashback["is_primary"] is False


def test_semimonthly_primary_income_sets_two_boundaries(client, today):
    user = register_and_login(client, "semicycle@example.com")
    ledger = personal_ledger(client, user)
    make_rule(
        client, user, ledger, kind="income", name="Зарплата", amount=45000,
        frequency="semimonthly", start_on="2026-09-05", day_of_month=5, second_day_of_month=20,
    )
    switch_mode(client, user, ledger, "income")
    data = cycles(client, user, ledger, count=2)
    assert [(c["start"], c["end"]) for c in data["cycles"]] == [
        ("2026-10-20", "2026-11-04"),
        ("2026-11-05", "2026-11-19"),
    ]


# ------------------------------------------------------------- итоги периода и права


def test_period_summary_follows_mode(client, today):
    user = register_and_login(client, "psum@example.com")
    ledger = personal_ledger(client, user)
    setup_two_incomes(client, user, ledger)
    confirm_income(client, user, ledger, "Аванс", "2026-10-10")
    confirm_income(client, user, ledger, "Зарплата", "2026-10-25")

    month = client.get(f"/finance/ledgers/{ledger}/period-summary", headers=user["headers"]).json()
    assert (month["start"], month["end"]) == ("2026-10-01", "2026-10-31")
    assert dec(month["income"]) == Decimal("140000")  # аванс и зарплата октября

    switch_mode(client, user, ledger, "income")
    cycle = client.get(f"/finance/ledgers/{ledger}/period-summary", headers=user["headers"]).json()
    assert (cycle["start"], cycle["end"]) == ("2026-10-25", "2026-11-09")
    assert dec(cycle["income"]) == Decimal("90000")
    other_day = client.get(
        f"/finance/ledgers/{ledger}/period-summary", params={"on": "2026-10-12"}, headers=user["headers"]
    ).json()
    assert (other_day["start"], other_day["end"]) == ("2026-10-10", "2026-10-24")
    assert dec(other_day["income"]) == Decimal("50000")


def test_only_managers_switch_mode_in_household(client, today):
    owner = register_and_login(client, "co@example.com")
    member = register_and_login(client, "cm@example.com")
    household_id = new_household(client, owner, member)
    ledger = household_ledger(client, owner, household_id)
    assert switch_mode(client, member, ledger, "income").status_code == 403
    assert switch_mode(client, owner, ledger, "income").status_code == 200
    listing = client.get("/finance/ledgers", headers=member["headers"]).json()
    assert listing[0]["cycle_mode"] == "income"
    assert switch_mode(client, owner, ledger, "weekly").status_code == 422


# ------------------------------------------------------------- долговая нагрузка


def test_load_example_from_the_product_note(client, today):
    """Зарплата 140 000 ₽, обязательные платежи 100 000 ₽: нагрузка высокая, новые долги не рекомендуются."""
    user = register_and_login(client, "load@example.com")
    ledger = personal_ledger(client, user)
    make_rule(client, user, ledger, kind="income", name="Зарплата", amount=140000, start_on="2026-10-25")
    make_rule(client, user, ledger, name="Аренда", amount=60000, start_on="2026-11-03")
    make_rule(client, user, ledger, name="Кредиты", amount=30000, start_on="2026-11-12")
    make_rule(client, user, ledger, name="Связь и коммунальные", amount=10000, start_on="2026-11-20")

    load = client.get(f"/finance/ledgers/{ledger}/load", headers=user["headers"]).json()
    assert dec(load["income_monthly"]) == Decimal("140000")
    assert dec(load["mandatory_monthly"]) == Decimal("100000")
    assert dec(load["free_monthly"]) == Decimal("40000")
    assert load["mandatory_share"] == 71.4
    assert load["status"] == "high"
    assert dec(load["safe_extra_payment"]) == 0
    assert dec(load["emergency_fund_target"]) == Decimal("300000")
    assert [item["name"] for item in load["mandatory_items"]] == ["Аренда", "Кредиты", "Связь и коммунальные"]
    codes = {item["code"] for item in load["advice"]}
    assert {"no_new_debt", "review_biggest", "emergency_fund"} <= codes
    text = next(item["text"] for item in load["advice"] if item["code"] == "no_new_debt")
    assert "71 %" in text and "40" in text

    simulated = client.get(
        f"/finance/ledgers/{ledger}/load/simulate", params={"payment": 15000}, headers=user["headers"]
    ).json()
    assert simulated["verdict"] == "not_recommended"
    assert simulated["new_mandatory_share"] == 82.1
    assert dec(simulated["new_free_monthly"]) == Decimal("25000")
    assert "не рекомендуется" in simulated["text"]


def test_load_comfortable_and_simulation_verdicts(client, today):
    user = register_and_login(client, "comfy@example.com")
    ledger = personal_ledger(client, user)
    make_rule(client, user, ledger, kind="income", name="Зарплата", amount=140000, start_on="2026-10-25")
    make_rule(client, user, ledger, name="Аренда", amount=40000, start_on="2026-11-03")

    load = client.get(f"/finance/ledgers/{ledger}/load", headers=user["headers"]).json()
    assert load["status"] == "comfortable" and load["mandatory_share"] == 28.6
    assert dec(load["safe_extra_payment"]) == Decimal("30000")  # 50 % дохода = 70 000, обязательных 40 000

    def verdict(payment):
        response = client.get(
            f"/finance/ledgers/{ledger}/load/simulate", params={"payment": payment}, headers=user["headers"]
        )
        assert response.status_code == 200, response.text
        return response.json()["verdict"]

    assert verdict(20000) == "ok"  # 60 000 / 140 000 = 42,9 %
    assert verdict(40000) == "risky"  # 80 000 / 140 000 = 57,1 %
    assert verdict(70000) == "not_recommended"  # 78,6 %


def test_load_normalizes_weekly_and_yearly_amounts(client, today):
    user = register_and_login(client, "norm@example.com")
    ledger = personal_ledger(client, user)
    make_rule(client, user, ledger, kind="income", name="Зарплата", amount=100000, start_on="2026-10-25")
    make_rule(client, user, ledger, name="Бассейн", amount=1000, frequency="weekly", start_on="2026-11-02")
    make_rule(client, user, ledger, name="Страховка", amount=12000, frequency="yearly", start_on="2027-03-01")
    load = client.get(f"/finance/ledgers/{ledger}/load", headers=user["headers"]).json()
    # 1000 × 52 / 12 = 4333,33 и 12 000 / 12 = 1000
    assert dec(load["mandatory_monthly"]) == Decimal("5333.33")


def test_load_without_income(client, today):
    user = register_and_login(client, "noinc@example.com")
    ledger = personal_ledger(client, user)
    make_rule(client, user, ledger, name="Аренда", amount=40000, start_on="2026-11-03")
    load = client.get(f"/finance/ledgers/{ledger}/load", headers=user["headers"]).json()
    assert load["status"] == "no_income" and load["mandatory_share"] is None
    simulated = client.get(
        f"/finance/ledgers/{ledger}/load/simulate", params={"payment": 5000}, headers=user["headers"]
    ).json()
    assert simulated["verdict"] == "not_recommended" and simulated["new_mandatory_share"] is None


def test_load_uses_average_of_other_spending(client, today):
    user = register_and_login(client, "avg@example.com")
    ledger = personal_ledger(client, user)
    make_rule(client, user, ledger, kind="income", name="Зарплата", amount=100000, start_on="2026-10-25")
    make_rule(client, user, ledger, name="Аренда", amount=30000, start_on="2026-11-03")
    categories = client.get(f"/finance/ledgers/{ledger}/categories", headers=user["headers"]).json()
    groceries = next(c["id"] for c in categories if c["name"] == "Продукты")
    for day, amount in (("2026-09-10", 20000), ("2026-08-15", 30000), ("2026-10-05", 99999)):
        client.post(
            f"/finance/ledgers/{ledger}/transactions",
            json={"category_id": groceries, "amount": amount, "occurred_on": day},
            headers=user["headers"],
        )
    load = client.get(f"/finance/ledgers/{ledger}/load", headers=user["headers"]).json()
    # Текущий месяц не учитывается: (20 000 + 30 000) / 2
    assert dec(load["avg_other_expense_monthly"]) == Decimal("25000")
    assert dec(load["left_after_expenses"]) == Decimal("45000")
    # Безопасный платёж ограничен остатком после трат: 50 % дохода − 30 000 = 20 000 < 45 000
    assert dec(load["safe_extra_payment"]) == Decimal("20000")


def test_simulation_requires_positive_payment(client, today):
    user = register_and_login(client, "simv@example.com")
    ledger = personal_ledger(client, user)
    base = f"/finance/ledgers/{ledger}/load/simulate"
    assert client.get(base, headers=user["headers"]).status_code == 422
    assert client.get(base, params={"payment": 0}, headers=user["headers"]).status_code == 422
    assert client.get(base, params={"payment": -10}, headers=user["headers"]).status_code == 422
