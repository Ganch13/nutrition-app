"""Сводные расходы за период (пункт 5 ТЗ от 29.10.2026). Сегодня по фикстуре — 28 октября 2026."""

from decimal import Decimal

from tests.finance_plan_helpers import (  # noqa: F401  (today — фикстура)
    household_ledger,
    make_rule,
    new_household,
    personal_ledger,
    register_and_login,
    today,
)
from tests.test_finance_goal_links import category, goal, make_goal, operations, spend
from tests.test_home import home


def dec(value) -> Decimal:
    return Decimal(str(value))


WEEK = {"period_start": "2026-10-19", "period_end": "2026-10-25"}


def lines(client, user, ledger: int, *pairs) -> list[dict]:
    """[("Продукты", 8000), ("Транспорт", 1200)] → [{"category_id": 3, "amount": 8000}, ...]"""
    return [{"category_id": category(client, user, ledger, name), "amount": amount} for name, amount in pairs]


def check(client, user, ledger: int, body: dict):
    return client.post(f"/finance/ledgers/{ledger}/summaries/check", json=body, headers=user["headers"])


def create(client, user, ledger: int, body: dict):
    return client.post(f"/finance/ledgers/{ledger}/summaries", json=body, headers=user["headers"])


def balance(client, user, ledger: int) -> Decimal:
    return dec(next(i for i in home(client, user) if i["ledger_id"] == ledger)["total"])


def test_summary_without_overlap(client, today):
    user = register_and_login(client, "summary@example.com")
    ledger = personal_ledger(client, user)
    body = {**WEEK, "lines": lines(client, user, ledger, ("Продукты", 8000), ("Транспорт", 1200)), "note": "Чеки"}

    result = check(client, user, ledger, body).json()
    assert result["matches"] == [] and dec(result["summary_total"]) == Decimal("9200")

    response = create(client, user, ledger, body)
    assert response.status_code == 201, response.text
    summary = response.json()
    assert dec(summary["total"]) == Decimal("9200") and len(summary["lines"]) == 2
    assert all(line["occurred_on"] == "2026-10-25" and line["description"] == "Чеки" for line in summary["lines"])

    # Баланс и отчёт считают сводку как обычные расходы
    assert balance(client, user, ledger) == Decimal("-9200")
    report = client.get(f"/finance/ledgers/{ledger}/summary?month=2026-10", headers=user["headers"]).json()
    assert dec(report["expense"]) == Decimal("9200")
    # В операциях строки помечены периодом сводки
    assert {(op["summary_start"], op["summary_end"]) for op in operations(client, user, ledger)} == {
        ("2026-10-19", "2026-10-25")
    }


def test_overlap_asks_and_respects_choice(client, today):
    user = register_and_login(client, "summary-overlap@example.com")
    ledger = personal_ledger(client, user)
    shop = spend(client, user, ledger, 1850, occurred_on="2026-10-20", name="Продукты").json()
    market = spend(client, user, ledger, 2600, occurred_on="2026-10-24", name="Продукты").json()
    taxi = spend(client, user, ledger, 450, occurred_on="2026-10-21", name="Развлечения").json()  # другая категория
    outside = spend(client, user, ledger, 700, occurred_on="2026-10-26", name="Продукты").json()  # вне периода
    make_rule(client, user, ledger, name="Подписка", amount=300, start_on="2026-10-22", auto_post=True,
              category_id=category(client, user, ledger, "Продукты"))
    body = {**WEEK, "lines": lines(client, user, ledger, ("Продукты", 9200))}

    # Сверка видит только две покупки «Продукты» за период (автосписание и другие категории — нет)
    result = check(client, user, ledger, body).json()
    assert [m["transaction_id"] for m in result["matches"]] == [shop["id"], market["id"]]
    assert dec(result["existing_total"]) == Decimal("4450") and result["existing_count"] == 2

    # Без выбора — 409, ничего не сохранено
    before = operations(client, user, ledger)
    response = create(client, user, ledger, body)
    assert response.status_code == 409
    # money() ставит неразрывные пробелы (\xa0), для сравнения заменяем их обычными
    detail = response.json()["detail"].replace("\xa0", " ")
    assert "уже записано 4 450 ₽" in detail and "сводка на 9 200 ₽" in detail
    assert operations(client, user, ledger) == before

    # Замена: удалены ровно показанные операции, остальные целы
    response = create(client, user, ledger, {**body, "mode": "replace", "replace_ids": [shop["id"], market["id"]]})
    assert response.status_code == 201, response.text
    assert response.json()["replaced_count"] == 2
    ids = {op["id"] for op in operations(client, user, ledger)}
    assert shop["id"] not in ids and market["id"] not in ids
    assert {taxi["id"], outside["id"]} <= ids

    # Повторная сводка за тот же период: прежняя сводка сама считается возможным повтором; дополнение — ничего не удаляет
    result = check(client, user, ledger, body).json()
    assert result["existing_count"] == 1 and result["matches"][0]["summary_id"] == response.json()["id"]
    response = create(client, user, ledger, {**body, "mode": "add"})
    assert response.status_code == 201 and response.json()["replaced_count"] == 0
    assert len([op for op in operations(client, user, ledger) if op["summary_id"]]) == 2


def test_replace_only_shown_operations(client, today):
    user = register_and_login(client, "summary-replace@example.com")
    ledger = personal_ledger(client, user)
    other = spend(client, user, ledger, 300, occurred_on="2026-10-20", name="Развлечения").json()
    spend(client, user, ledger, 500, occurred_on="2026-10-20", name="Продукты")
    body = {**WEEK, "lines": lines(client, user, ledger, ("Продукты", 1000))}

    # Операция другой категории не показывалась при сверке — заменить её нельзя
    response = create(client, user, ledger, {**body, "mode": "replace", "replace_ids": [other["id"]]})
    assert response.status_code == 422
    assert other["id"] in {op["id"] for op in operations(client, user, ledger)}


def test_summary_line_with_goal_and_delete(client, today):
    user = register_and_login(client, "summary-goal@example.com")
    ledger = personal_ledger(client, user)
    vacation = make_goal(client, user, ledger, kind="savings", name="Отпуск", target_amount=200000)
    body = {**WEEK, "lines": [*lines(client, user, ledger, ("Продукты", 3000)),
                              {"category_id": category(client, user, ledger, "Другое"), "amount": 5000,
                               "goal_id": vacation["id"]}]}

    summary = create(client, user, ledger, body).json()
    assert dec(goal(client, user, ledger, vacation["id"])["paid_total"]) == Decimal("5000")
    assert balance(client, user, ledger) == Decimal("-8000")
    assert [line["goal_name"] for line in summary["lines"]] == [None, "Отпуск"]

    # Удаление сводки целиком откатывает баланс и цель
    response = client.delete(f"/finance/ledgers/{ledger}/summaries/{summary['id']}", headers=user["headers"])
    assert response.status_code == 204
    assert balance(client, user, ledger) == 0
    assert dec(goal(client, user, ledger, vacation["id"])["paid_total"]) == 0
    assert client.get(f"/finance/ledgers/{ledger}/summaries", headers=user["headers"]).json() == []


def test_summary_validation_and_permissions(client, today):
    owner = register_and_login(client, "summary-owner@example.com")
    member = register_and_login(client, "summary-member@example.com")
    family = household_ledger(client, owner, new_household(client, owner, member))
    personal = personal_ledger(client, owner)
    groceries = lines(client, owner, family, ("Продукты", 100))

    # Будущий период, доход вместо расхода, начало позже конца
    assert check(client, owner, family, {"period_start": "2026-10-26", "period_end": "2026-11-01",
                                         "lines": groceries}).status_code == 422
    salary = [{"category_id": category(client, owner, family, "Зарплата"), "amount": 100}]
    assert check(client, owner, family, {**WEEK, "lines": salary}).status_code == 422
    assert check(client, owner, family, {"period_start": "2026-10-25", "period_end": "2026-10-19",
                                         "lines": groceries}).status_code == 422
    # Категория чужой книги
    assert check(client, owner, personal, {**WEEK, "lines": groceries}).status_code == 404

    # Участник не может заменить чужую покупку и удалить чужую сводку
    owner_purchase = spend(client, owner, family, 400, occurred_on="2026-10-20", name="Продукты").json()
    response = create(client, member, family, {**WEEK, "lines": groceries, "mode": "replace",
                                               "replace_ids": [owner_purchase["id"]]})
    assert response.status_code == 403
    owner_summary = create(client, owner, family, {**WEEK, "lines": groceries, "mode": "add"}).json()
    response = client.delete(f"/finance/ledgers/{family}/summaries/{owner_summary['id']}", headers=member["headers"])
    assert response.status_code == 403
