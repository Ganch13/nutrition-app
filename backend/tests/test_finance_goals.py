"""Финансовые цели: накопления, простые долги, кредиты с процентами, совместные цели."""

from datetime import date
from decimal import Decimal

from tests.finance_plan_helpers import (  # noqa: F401  (today — фикстура)
    household_ledger,
    new_household,
    personal_ledger,
    register_and_login,
    today,
)


def dec(value) -> Decimal:
    return Decimal(str(value))


def goals_url(ledger: int, suffix: str = "") -> str:
    return f"/finance/ledgers/{ledger}/goals{suffix}"


def create(client, user, ledger, **fields):
    body = {"kind": "savings", "name": "Отпуск", "target_amount": 200000, **fields}
    return client.post(goals_url(ledger), json=body, headers=user["headers"])


def make(client, user, ledger, **fields) -> dict:
    response = create(client, user, ledger, **fields)
    assert response.status_code == 201, response.text
    return response.json()


def pay(client, user, ledger, goal_id, amount, paid_on=None, note=None):
    body = {"amount": amount}
    if paid_on:
        body["paid_on"] = paid_on
    if note:
        body["note"] = note
    return client.post(goals_url(ledger, f"/{goal_id}/entries"), json=body, headers=user["headers"])


def make_loan(client, user, ledger, **fields) -> dict:
    return make(
        client, user, ledger,
        kind="loan", name="Кредит в банке", target_amount=100000, interest_rate=60, payment_day=15, **fields,
    )


# ------------------------------------------------------------- накопления


def test_savings_goal_progress(client, today):
    user = register_and_login(client, "save@example.com")
    ledger = personal_ledger(client, user)
    goal = make(client, user, ledger, start_amount=15000)

    assert goal["kind"] == "savings" and goal["shared"] is False and goal["can_edit"] is True
    assert dec(goal["remaining"]) == Decimal("185000") and goal["progress"] == 0.075 and goal["done"] is False

    assert pay(client, user, ledger, goal["id"], 20000, "2026-10-10").status_code == 201
    detail = pay(client, user, ledger, goal["id"], 5000, "2026-10-20", note="Премия").json()
    assert dec(detail["paid_total"]) == Decimal("40000")
    assert dec(detail["remaining"]) == Decimal("160000")
    assert detail["progress"] == 0.2
    # История: новые сверху, у накопления проценты не считаются
    assert [(e["paid_on"], dec(e["amount"]), e["note"]) for e in detail["entries"]] == [
        ("2026-10-20", Decimal("5000"), "Премия"),
        ("2026-10-10", Decimal("20000"), None),
    ]
    assert detail["entries"][0]["interest_part"] is None and detail["last_interest"] is None


def test_savings_goal_can_be_completed_and_exceeded(client, today):
    user = register_and_login(client, "done@example.com")
    ledger = personal_ledger(client, user)
    goal = make(client, user, ledger, target_amount=1000)
    detail = pay(client, user, ledger, goal["id"], 1000).json()
    assert detail["done"] is True and dec(detail["remaining"]) == 0 and detail["progress"] == 1.0
    # В накопление можно вносить и дальше
    detail = pay(client, user, ledger, goal["id"], 500).json()
    assert detail["done"] is True and dec(detail["paid_total"]) == Decimal("1500") and detail["progress"] == 1.0


def test_entry_defaults_to_today_and_rejects_future_dates(client, today):
    user = register_and_login(client, "dates@example.com")
    ledger = personal_ledger(client, user)
    goal = make(client, user, ledger)
    detail = pay(client, user, ledger, goal["id"], 100).json()
    assert detail["entries"][0]["paid_on"] == "2026-10-28"
    assert pay(client, user, ledger, goal["id"], 100, "2026-10-29").status_code == 422


def test_delete_entry_recalculates(client, today):
    user = register_and_login(client, "unpay@example.com")
    ledger = personal_ledger(client, user)
    goal = make(client, user, ledger)
    detail = pay(client, user, ledger, goal["id"], 1000).json()
    entry_id = detail["entries"][0]["id"]
    response = client.delete(goals_url(ledger, f"/{goal['id']}/entries/{entry_id}"), headers=user["headers"])
    assert response.status_code == 200 and dec(response.json()["paid_total"]) == 0
    assert client.delete(goals_url(ledger, f"/{goal['id']}/entries/{entry_id}"), headers=user["headers"]).status_code == 404


# ------------------------------------------------------------- простой долг


def test_plain_debt(client, today):
    user = register_and_login(client, "debt@example.com")
    ledger = personal_ledger(client, user)
    goal = make(client, user, ledger, kind="debt", name="Долг Ивану", target_amount=30000, start_amount=5000)
    assert dec(goal["remaining"]) == Decimal("25000") and dec(goal["paid_total"]) == Decimal("5000")

    detail = pay(client, user, ledger, goal["id"], 10000).json()
    # Каждый рубль уменьшает долг целиком, проценты не начисляются
    assert dec(detail["remaining"]) == Decimal("15000")
    assert detail["entries"][0]["interest_part"] is None and detail["entries"][0]["balance_after"] is None

    too_much = pay(client, user, ledger, goal["id"], 15000.01)
    assert too_much.status_code == 422 and "не более 15" in too_much.json()["detail"]

    assert pay(client, user, ledger, goal["id"], 15000).json()["done"] is True
    closed = pay(client, user, ledger, goal["id"], 1)
    assert closed.status_code == 409


# ------------------------------------------------------------- кредит


def test_loan_payment_is_split_into_interest_and_principal(client, today):
    """Пример из ТЗ: долг 100 000 ₽ под 60 % годовых, платёж 20 000 ₽."""
    user = register_and_login(client, "loan@example.com")
    ledger = personal_ledger(client, user)
    goal = make_loan(client, user, ledger)
    assert dec(goal["remaining"]) == Decimal("100000") and goal["next_payment_on"] == "2026-11-15"

    detail = pay(client, user, ledger, goal["id"], 20000, "2026-10-15").json()
    entry = detail["entries"][0]
    assert dec(entry["interest_part"]) == Decimal("5000")
    assert dec(entry["principal_part"]) == Decimal("15000")
    assert dec(entry["balance_after"]) == Decimal("85000")
    assert dec(detail["remaining"]) == Decimal("85000")  # а не 80 000
    assert dec(detail["last_interest"]) == Decimal("5000")
    assert dec(detail["interest_paid_total"]) == Decimal("5000")
    assert dec(detail["paid_total"]) == Decimal("20000")
    assert detail["progress"] == 0.15

    # Второй платёж считается от нового остатка: 85 000 × 5 % = 4 250
    second = pay(client, user, ledger, goal["id"], 20000, "2026-10-20")
    assert second.status_code == 201, second.text
    latest = second.json()["entries"][0]
    assert dec(latest["interest_part"]) == Decimal("4250")
    assert dec(latest["principal_part"]) == Decimal("15750")
    assert dec(latest["balance_after"]) == Decimal("69250")


def test_loan_recalculates_when_earlier_payment_is_removed(client, today):
    user = register_and_login(client, "recalc@example.com")
    ledger = personal_ledger(client, user)
    goal = make_loan(client, user, ledger)
    pay(client, user, ledger, goal["id"], 20000, "2026-09-15")
    detail = pay(client, user, ledger, goal["id"], 20000, "2026-10-15").json()
    first, second = detail["entries"][1], detail["entries"][0]
    assert dec(second["balance_after"]) == Decimal("69250")

    removed = client.delete(goals_url(ledger, f"/{goal['id']}/entries/{first['id']}"), headers=user["headers"])
    assert removed.status_code == 200
    only = removed.json()["entries"][0]
    # Остался один платёж, проценты за него теперь считаются с полного долга
    assert dec(only["interest_part"]) == Decimal("5000") and dec(only["balance_after"]) == Decimal("85000")


def test_loan_back_dated_payment_is_inserted_in_order(client, today):
    user = register_and_login(client, "order@example.com")
    ledger = personal_ledger(client, user)
    goal = make_loan(client, user, ledger)
    pay(client, user, ledger, goal["id"], 20000, "2026-10-15")
    detail = pay(client, user, ledger, goal["id"], 20000, "2026-09-15").json()
    by_date = {e["paid_on"]: e for e in detail["entries"]}
    assert dec(by_date["2026-09-15"]["balance_after"]) == Decimal("85000")
    assert dec(by_date["2026-10-15"]["interest_part"]) == Decimal("4250")
    assert dec(detail["remaining"]) == Decimal("69250")


def test_loan_full_repayment_and_overpayment(client, today):
    user = register_and_login(client, "full@example.com")
    ledger = personal_ledger(client, user)
    goal = make_loan(client, user, ledger)
    # Максимум за один платёж: долг + проценты = 100 000 + 5 000
    too_much = pay(client, user, ledger, goal["id"], 105000.01)
    assert too_much.status_code == 422 and "105" in too_much.json()["detail"]
    final = pay(client, user, ledger, goal["id"], 105000).json()
    assert final["done"] is True and dec(final["remaining"]) == 0 and final["next_payment_on"] is None
    assert pay(client, user, ledger, goal["id"], 100).status_code == 409


def test_loan_payment_smaller_than_interest_grows_the_debt(client, today):
    user = register_and_login(client, "small@example.com")
    ledger = personal_ledger(client, user)
    goal = make_loan(client, user, ledger)
    detail = pay(client, user, ledger, goal["id"], 3000).json()
    entry = detail["entries"][0]
    assert dec(entry["interest_part"]) == Decimal("5000") and dec(entry["principal_part"]) == Decimal("-2000")
    assert dec(detail["remaining"]) == Decimal("102000")
    assert detail["progress"] == 0.0


def test_loan_requires_rate_and_payment_day(client, today):
    user = register_and_login(client, "loanval@example.com")
    ledger = personal_ledger(client, user)
    assert create(client, user, ledger, kind="loan", target_amount=1000).status_code == 422
    assert create(client, user, ledger, kind="loan", target_amount=1000, interest_rate=10).status_code == 422
    assert create(client, user, ledger, kind="loan", target_amount=1000, payment_day=5).status_code == 422
    assert create(client, user, ledger, kind="loan", target_amount=1000, interest_rate=10, payment_day=32).status_code == 422
    assert create(client, user, ledger, kind="loan", target_amount=1000, interest_rate=-1, payment_day=5).status_code == 422
    assert create(client, user, ledger, kind="loan", target_amount=1000, interest_rate=10, payment_day=5, start_amount=50).status_code == 422
    # Ставка вне кредита не нужна
    assert create(client, user, ledger, kind="savings", interest_rate=10).status_code == 422
    assert create(client, user, ledger, kind="debt", target_amount=100, start_amount=101).status_code == 422
    assert create(client, user, ledger, target_amount=0).status_code == 422
    assert create(client, user, ledger, name="  ").status_code == 422
    assert create(client, user, ledger, kind="mortgage").status_code == 422


def test_next_payment_date_clamps_to_month_end(client, today):
    user = register_and_login(client, "clamp@example.com")
    ledger = personal_ledger(client, user)
    goal = make(client, user, ledger, kind="loan", name="Кредит", target_amount=1000, interest_rate=12, payment_day=31)
    assert goal["next_payment_on"] == "2026-10-31"
    today["day"] = date(2026, 11, 2)
    listing = client.get(goals_url(ledger), headers=user["headers"]).json()
    assert listing[0]["next_payment_on"] == "2026-11-30"


# ------------------------------------------------------------- изменение и удаление


def test_update_goal_and_recalculate_loan(client, today):
    user = register_and_login(client, "edit@example.com")
    ledger = personal_ledger(client, user)
    goal = make_loan(client, user, ledger)
    pay(client, user, ledger, goal["id"], 20000, "2026-10-15")
    url = goals_url(ledger, f"/{goal['id']}")

    renamed = client.patch(url, json={"name": "Кредит на ремонт"}, headers=user["headers"])
    assert renamed.status_code == 200 and renamed.json()["name"] == "Кредит на ремонт"

    # Ставка 24 % → проценты 100 000 × 2 % = 2 000, остаток пересчитан
    changed = client.patch(url, json={"interest_rate": 24}, headers=user["headers"])
    assert changed.status_code == 200
    assert dec(changed.json()["remaining"]) == Decimal("82000")
    assert dec(changed.json()["last_interest"]) == Decimal("2000")

    # Уменьшить долг так, чтобы уже внесённые платежи не помещались, нельзя
    assert client.patch(url, json={"target_amount": 1000}, headers=user["headers"]).status_code == 422
    assert client.patch(url, json={"start_amount": 500}, headers=user["headers"]).status_code == 422
    assert client.patch(url, json={"interest_rate": None}, headers=user["headers"]).status_code == 422
    assert dec(client.get(url, headers=user["headers"]).json()["remaining"]) == Decimal("82000")


def test_update_savings_rejects_loan_fields(client, today):
    user = register_and_login(client, "editsave@example.com")
    ledger = personal_ledger(client, user)
    goal = make(client, user, ledger)
    url = goals_url(ledger, f"/{goal['id']}")
    assert client.patch(url, json={"interest_rate": 10}, headers=user["headers"]).status_code == 422
    changed = client.patch(url, json={"target_amount": 250000}, headers=user["headers"])
    assert changed.status_code == 200 and dec(changed.json()["target_amount"]) == Decimal("250000")


def test_delete_goal_removes_entries(client, today):
    user = register_and_login(client, "rmgoal@example.com")
    ledger = personal_ledger(client, user)
    goal = make(client, user, ledger)
    pay(client, user, ledger, goal["id"], 100)
    url = goals_url(ledger, f"/{goal['id']}")
    assert client.delete(url, headers=user["headers"]).status_code == 204
    assert client.get(url, headers=user["headers"]).status_code == 404
    assert client.get(goals_url(ledger), headers=user["headers"]).json() == []


def test_done_goals_go_last(client, today):
    user = register_and_login(client, "sort@example.com")
    ledger = personal_ledger(client, user)
    finished = make(client, user, ledger, name="Готовая", target_amount=100)
    pay(client, user, ledger, finished["id"], 100)
    active = make(client, user, ledger, name="Активная")
    assert [g["name"] for g in client.get(goals_url(ledger), headers=user["headers"]).json()] == ["Активная", "Готовая"]
    assert active["id"] != finished["id"]


# ------------------------------------------------------------- личные и совместные цели


def test_personal_goals_are_private(client, today):
    user = register_and_login(client, "priv@example.com")
    friend = register_and_login(client, "priv2@example.com")
    ledger = personal_ledger(client, user)
    goal = make(client, user, ledger)
    assert client.get(goals_url(ledger), headers=friend["headers"]).status_code == 404
    assert client.get(goals_url(ledger, f"/{goal['id']}"), headers=friend["headers"]).status_code == 404
    assert pay(client, friend, ledger, goal["id"], 100).status_code == 404
    # Чужая цель по id в своей книге не находится
    friend_ledger = personal_ledger(client, friend)
    assert client.get(goals_url(friend_ledger, f"/{goal['id']}"), headers=friend["headers"]).status_code == 404
    assert pay(client, friend, friend_ledger, goal["id"], 100).status_code == 404


def test_shared_goal_splits_progress_by_author(client, today):
    owner = register_and_login(client, "so@example.com", "Даня")
    wife = register_and_login(client, "sw@example.com", "Леся")
    household_id = new_household(client, owner, wife)
    ledger = household_ledger(client, owner, household_id)

    goal = make(client, owner, ledger, name="Отпуск вдвоём", target_amount=100000, start_amount=10000)
    assert goal["shared"] is True
    pay(client, owner, ledger, goal["id"], 20000, "2026-10-10")
    detail = pay(client, wife, ledger, goal["id"], 10000, "2026-10-12").json()

    # Стартовые 10 000 записаны автору цели, поэтому у Дани 30 000, у Леси 10 000
    shares = {c["name"]: (dec(c["total"]), c["share"]) for c in detail["contributors"]}
    assert shares == {"Даня": (Decimal("30000"), 0.75), "Леся": (Decimal("10000"), 0.25)}
    assert dec(detail["paid_total"]) == Decimal("40000") and detail["progress"] == 0.4

    # Леся видит ту же цель в списке
    listing = client.get(goals_url(ledger), headers=wife["headers"]).json()
    assert [dec(c["total"]) for c in listing[0]["contributors"]] == [Decimal("30000"), Decimal("10000")]
    assert listing[0]["can_edit"] is False


def test_shared_goal_permissions(client, today):
    owner = register_and_login(client, "gpo@example.com", "Даня")
    wife = register_and_login(client, "gpw@example.com", "Леся")
    outsider = register_and_login(client, "gpx@example.com")
    household_id = new_household(client, owner, wife)
    ledger = household_ledger(client, owner, household_id)
    goal = make(client, owner, ledger, name="Машина")
    url = goals_url(ledger, f"/{goal['id']}")

    # Участница не может изменить и удалить чужую цель, но может вносить взносы
    assert client.patch(url, json={"name": "Другое"}, headers=wife["headers"]).status_code == 403
    assert client.delete(url, headers=wife["headers"]).status_code == 403
    detail = pay(client, wife, ledger, goal["id"], 1000).json()
    wife_entry = detail["entries"][0]
    assert wife_entry["can_delete"] is True and wife_entry["user_name"] == "Леся"

    owner_entry = pay(client, owner, ledger, goal["id"], 2000).json()["entries"][0]
    # Чужой взнос участница удалить не может, свой может; владелец может любой
    assert client.delete(f"{url}/entries/{owner_entry['id']}", headers=wife["headers"]).status_code == 403
    assert client.delete(f"{url}/entries/{wife_entry['id']}", headers=wife["headers"]).status_code == 200
    assert client.delete(f"{url}/entries/{owner_entry['id']}", headers=owner["headers"]).status_code == 200

    # Цель, созданную участницей, владелец семьи удалить может
    wives_goal = make(client, wife, ledger, name="Подарок")
    assert client.delete(goals_url(ledger, f"/{wives_goal['id']}"), headers=owner["headers"]).status_code == 204

    # Посторонний ничего не видит
    assert client.get(url, headers=outsider["headers"]).status_code == 404
    assert pay(client, outsider, ledger, goal["id"], 5).status_code == 404


def test_leaving_family_keeps_goal_with_deleted_author_name(client, today):
    """Если участник удалил аккаунт, его взносы остаются и подписаны «Удалённый пользователь»."""
    owner = register_and_login(client, "lo@example.com", "Даня")
    wife = register_and_login(client, "lw@example.com", "Леся")
    household_id = new_household(client, owner, wife)
    ledger = household_ledger(client, owner, household_id)
    goal = make(client, owner, ledger, name="Ремонт", target_amount=50000)
    pay(client, wife, ledger, goal["id"], 7000)
    pay(client, owner, ledger, goal["id"], 3000)

    deleted = client.post("/auth/delete-account", json={"password": "very-strong-password-123"}, headers=wife["headers"])
    assert deleted.status_code == 204

    detail = client.get(goals_url(ledger, f"/{goal['id']}"), headers=owner["headers"]).json()
    assert dec(detail["paid_total"]) == Decimal("10000")
    names = {c["name"]: dec(c["total"]) for c in detail["contributors"]}
    assert names == {"Даня": Decimal("3000"), "Удалённый пользователь": Decimal("7000")}
    assert {e["user_name"] for e in detail["entries"]} == {"Даня", "Удалённый пользователь"}


def test_owner_deleting_account_keeps_shared_goal_for_family(client, today):
    owner = register_and_login(client, "ko@example.com", "Даня")
    wife = register_and_login(client, "kw@example.com", "Леся")
    household_id = new_household(client, owner, wife)
    ledger = household_ledger(client, owner, household_id)
    goal = make(client, owner, ledger, name="Квартира", start_amount=1000)
    pay(client, owner, ledger, goal["id"], 2000)

    client.post("/auth/delete-account", json={"password": "very-strong-password-123"}, headers=owner["headers"])

    detail = client.get(goals_url(ledger, f"/{goal['id']}"), headers=wife["headers"]).json()
    assert dec(detail["paid_total"]) == Decimal("3000")
    # Леся стала владельцем семьи и поэтому может управлять целью без автора
    assert detail["can_edit"] is True and detail["created_by_user_id"] is None
