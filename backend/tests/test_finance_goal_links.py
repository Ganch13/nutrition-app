"""Расходы, отнесённые к целям (пункт 2 ТЗ от 29.10.2026). Сегодня по фикстуре — 28 октября 2026."""

from decimal import Decimal

from tests.finance_plan_helpers import (  # noqa: F401  (today — фикстура)
    household_ledger,
    new_household,
    personal_ledger,
    register_and_login,
    today,
)
from tests.test_home import home


def dec(value) -> Decimal:
    return Decimal(str(value))


def make_goal(client, user, ledger: int, **body) -> dict:
    response = client.post(f"/finance/ledgers/{ledger}/goals", json=body, headers=user["headers"])
    assert response.status_code == 201, response.text
    return response.json()


def goal(client, user, ledger: int, goal_id: int) -> dict:
    response = client.get(f"/finance/ledgers/{ledger}/goals/{goal_id}", headers=user["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def category(client, user, ledger: int, name: str) -> int:
    categories = client.get(f"/finance/ledgers/{ledger}/categories", headers=user["headers"]).json()
    return next(c["id"] for c in categories if c["name"] == name)


def spend(client, user, ledger: int, amount, goal_id=None, occurred_on="2026-10-28", name="Другое", **extra):
    """POST расхода (по умолчанию категория «Другое»); возвращает ответ целиком."""
    body = {"category_id": category(client, user, ledger, name), "amount": amount, "occurred_on": occurred_on, **extra}
    if goal_id is not None:
        body["goal_id"] = goal_id
    return client.post(f"/finance/ledgers/{ledger}/transactions", json=body, headers=user["headers"])


def patch(client, user, ledger: int, transaction_id: int, **body):
    return client.patch(f"/finance/ledgers/{ledger}/transactions/{transaction_id}", json=body, headers=user["headers"])


def operations(client, user, ledger: int) -> list[dict]:
    return client.get(f"/finance/ledgers/{ledger}/transactions?month=2026-10", headers=user["headers"]).json()


def test_expense_moves_savings_and_debt(client, today):
    user = register_and_login(client, "links@example.com")
    ledger = personal_ledger(client, user)
    vacation = make_goal(client, user, ledger, kind="savings", name="Отпуск", target_amount=200000, start_amount=15000)
    debt = make_goal(client, user, ledger, kind="debt", name="Долг Ивану", target_amount=30000, start_amount=5000)

    # Новая цель сразу доступна: расход на неё
    response = spend(client, user, ledger, 5000, vacation["id"], description="Отложил")
    assert response.status_code == 201, response.text
    expense = response.json()
    assert (expense["goal_id"], expense["goal_name"]) == (vacation["id"], "Отпуск")

    # Накопление выросло на ту же сумму, в истории — запись, связанная с расходом
    detail = goal(client, user, ledger, vacation["id"])
    assert dec(detail["paid_total"]) == Decimal("20000")
    [entry] = detail["entries"]
    assert entry["transaction_id"] == expense["id"] and dec(entry["amount"]) == Decimal("5000")
    assert entry["paid_on"] == "2026-10-28" and entry["note"] == "Отложил" and entry["can_delete"] is False

    # Долг уменьшился: осталось 25 000 − 4 000
    spend(client, user, ledger, 4000, debt["id"])
    assert dec(goal(client, user, ledger, debt["id"])["remaining"]) == Decimal("21000")

    # Расход виден в операциях с целью и уменьшает баланс
    linked = [op for op in operations(client, user, ledger) if op["goal_id"] is not None]
    assert {op["goal_name"] for op in linked} == {"Отпуск", "Долг Ивану"}
    assert dec(home(client, user)[0]["total"]) == Decimal("-9000")

    # Вручную удалить запись из истории цели нельзя: она меняется через расход
    response = client.delete(
        f"/finance/ledgers/{ledger}/goals/{vacation['id']}/entries/{entry['id']}", headers=user["headers"]
    )
    assert response.status_code == 409


def test_edit_and_delete_expense_updates_goal(client, today):
    user = register_and_login(client, "links-edit@example.com")
    ledger = personal_ledger(client, user)
    vacation = make_goal(client, user, ledger, kind="savings", name="Отпуск", target_amount=200000)
    car = make_goal(client, user, ledger, kind="savings", name="Машина", target_amount=500000)
    expense = spend(client, user, ledger, 5000, vacation["id"]).json()

    # Сумма 5 000 → 3 000: цель тоже
    response = patch(client, user, ledger, expense["id"], amount=3000)
    assert response.status_code == 200, response.text
    assert response.json()["goal_name"] == "Отпуск"
    assert dec(goal(client, user, ledger, vacation["id"])["paid_total"]) == Decimal("3000")

    # Перенос на другую цель
    patch(client, user, ledger, expense["id"], goal_id=car["id"])
    assert dec(goal(client, user, ledger, vacation["id"])["paid_total"]) == 0
    assert dec(goal(client, user, ledger, car["id"])["paid_total"]) == Decimal("3000")

    # Отвязать от цели: расход остался, цель откатилась
    response = patch(client, user, ledger, expense["id"], goal_id=None)
    assert response.json()["goal_id"] is None
    assert dec(goal(client, user, ledger, car["id"])["paid_total"]) == 0

    # Снова на цель и удалить расход — цель откатывается
    patch(client, user, ledger, expense["id"], goal_id=car["id"])
    assert client.delete(f"/finance/ledgers/{ledger}/transactions/{expense['id']}", headers=user["headers"]).status_code == 204
    detail = goal(client, user, ledger, car["id"])
    assert dec(detail["paid_total"]) == 0 and detail["entries"] == []


def test_loan_payment_from_expense(client, today):
    user = register_and_login(client, "links-loan@example.com")
    ledger = personal_ledger(client, user)
    loan = make_goal(client, user, ledger, kind="loan", name="Кредит", target_amount=100000, interest_rate=60, payment_day=15)

    expense = spend(client, user, ledger, 20000, loan["id"]).json()
    detail = goal(client, user, ledger, loan["id"])
    # Проценты 5 000, в тело долга 15 000
    assert dec(detail["remaining"]) == Decimal("85000")
    assert dec(detail["entries"][0]["interest_part"]) == Decimal("5000")

    patch(client, user, ledger, expense["id"], amount=10000)
    assert dec(goal(client, user, ledger, loan["id"])["remaining"]) == Decimal("95000")


def test_goal_rules_and_errors(client, today):
    owner = register_and_login(client, "links-owner@example.com")
    member = register_and_login(client, "links-member@example.com")
    personal = personal_ledger(client, owner)
    family = household_ledger(client, owner, new_household(client, owner, member))
    own_goal = make_goal(client, owner, personal, kind="savings", name="Личное", target_amount=1000)
    shared_goal = make_goal(client, owner, family, kind="debt", name="Общий долг", target_amount=10000)

    # Общая цель — только в семейной книге, личная — только в личной
    assert spend(client, owner, personal, 100, shared_goal["id"]).status_code == 404
    assert spend(client, owner, family, 100, own_goal["id"]).status_code == 404
    # Участник семьи вносит в общую цель, его доля видна
    assert spend(client, member, family, 2000, shared_goal["id"]).status_code == 201
    assert dec(goal(client, owner, family, shared_goal["id"])["remaining"]) == Decimal("8000")

    # Платёж больше остатка долга — 422, и сам расход не сохраняется
    before = len(operations(client, owner, family))
    response = spend(client, owner, family, 9000, shared_goal["id"])
    assert response.status_code == 422
    assert len(operations(client, owner, family)) == before

    # Доход с целью — 422; расход на цель в будущем — 422
    response = spend(client, owner, personal, 100, own_goal["id"], name="Зарплата")
    assert response.status_code == 422 and response.json()["detail"] == "Цель можно указать только у расхода"
    assert spend(client, owner, personal, 100, own_goal["id"], occurred_on="2026-11-02").status_code == 422

    # Чужую операцию участник менять не может
    owner_expense = spend(client, owner, family, 100).json()
    assert patch(client, member, family, owner_expense["id"], amount=50).status_code == 403


def test_deleting_goal_keeps_expense(client, today):
    user = register_and_login(client, "links-goal-delete@example.com")
    ledger = personal_ledger(client, user)
    vacation = make_goal(client, user, ledger, kind="savings", name="Отпуск", target_amount=200000)
    expense = spend(client, user, ledger, 5000, vacation["id"]).json()

    assert client.delete(f"/finance/ledgers/{ledger}/goals/{vacation['id']}", headers=user["headers"]).status_code == 204
    [op] = operations(client, user, ledger)
    assert op["id"] == expense["id"] and op["goal_id"] is None
    assert dec(home(client, user)[0]["total"]) == Decimal("-5000")
