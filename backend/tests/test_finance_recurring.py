"""Повторяющиеся доходы и обязательные платежи: правила, подтверждение поступлений, автосписание, права."""

from datetime import date
from decimal import Decimal

from tests.finance_plan_helpers import (  # noqa: F401  (today — фикстура)
    add_rule,
    confirm,
    household_ledger,
    make_rule,
    new_household,
    personal_ledger,
    register_and_login,
    today,
    transactions,
)


def amounts(items: list[dict]) -> list[Decimal]:
    return [Decimal(str(item["amount"])) for item in items]


def prompts(client, user) -> list[dict]:
    """Вопросы «Поступил ли платёж?» по всем книгам пользователя."""
    response = client.get("/finance/income-prompts", headers=user["headers"])
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------- подтверждение дохода


def test_income_is_not_posted_automatically(client, today):
    user = register_and_login(client, "inc@example.com")
    ledger = personal_ledger(client, user)

    # Аванс 10-го числа, правило действует с 10 сентября; сегодня 28 октября
    rule = make_rule(client, user, ledger, kind="income", name="Аванс", amount=50000, start_on="2026-09-10")

    assert rule["kind"] == "income"
    assert rule["auto_post"] is False
    assert rule["is_primary"] is True
    assert rule["end_on"] is None
    assert rule["day_of_month"] == 10
    assert rule["category_name"] == "Зарплата"
    assert rule["next_due_on"] == "2026-11-10"
    assert Decimal(str(rule["monthly_amount"])) == Decimal("50000")

    # Деньги не начисляются сами: прошедшие даты ждут ответа
    for _ in range(2):
        assert transactions(client, user, ledger, "2026-09") == []
        assert transactions(client, user, ledger, "2026-10") == []
    upcoming = client.get(f"/finance/ledgers/{ledger}/upcoming?days=30", headers=user["headers"]).json()
    assert [(item["due_on"], item["overdue"]) for item in upcoming] == [
        ("2026-09-10", True),
        ("2026-10-10", True),
        ("2026-11-10", False),
    ]


def test_income_cannot_be_auto_posted_or_have_end_date(client, today):
    user = register_and_login(client, "noauto@example.com")
    ledger = personal_ledger(client, user)
    assert add_rule(client, user, ledger, kind="income", auto_post=True).status_code == 422
    assert add_rule(client, user, ledger, kind="income", end_on="2027-01-01").status_code == 422

    rule = make_rule(client, user, ledger, kind="income", name="Зарплата", amount=90000, start_on="2026-10-25")
    url = f"/finance/ledgers/{ledger}/recurring/{rule['id']}"
    assert client.patch(url, json={"auto_post": True}, headers=user["headers"]).status_code == 422
    assert client.patch(url, json={"end_on": "2027-01-01"}, headers=user["headers"]).status_code == 422

    # У платежа дата окончания и автосписание по-прежнему есть
    payment = make_rule(client, user, ledger, name="Кредит", amount=5000, start_on="2026-11-01", end_on="2027-03-01", auto_post=True)
    assert payment["end_on"] == "2027-03-01" and payment["auto_post"] is True


def test_prompt_window_is_two_days_around_due_date(client, today):
    user = register_and_login(client, "window@example.com")
    ledger = personal_ledger(client, user)
    make_rule(client, user, ledger, kind="income", name="Зарплата", amount=90000, start_on="2026-09-25")
    make_rule(client, user, ledger, name="Аренда", amount=35000, start_on="2026-10-27")

    # Сегодня 28 октября: зарплата 25-го — уже три дня назад, спрашивать поздно; платежи не спрашиваются
    assert prompts(client, user) == []

    for day, expected in [(22, []), (23, ["2026-10-25"]), (25, ["2026-10-25"]), (27, ["2026-10-25"]), (28, [])]:
        today["day"] = date(2026, 10, day)
        assert [item["due_on"] for item in prompts(client, user)] == expected, day

    today["day"] = date(2026, 10, 24)
    item = prompts(client, user)[0]
    assert item["ledger_id"] == ledger and item["ledger_kind"] == "personal"
    assert item["rule_name"] == "Зарплата" and Decimal(str(item["planned_amount"])) == Decimal("90000")
    assert item["currency"] == "RUB" and item["is_primary"] is True


def test_yes_with_actual_date_and_amount_closes_prompt(client, today):
    user = register_and_login(client, "yes@example.com")
    ledger = personal_ledger(client, user)
    rule = make_rule(client, user, ledger, kind="income", name="Зарплата", amount=90000, start_on="2026-10-25")
    today["day"] = date(2026, 10, 26)
    assert len(prompts(client, user)) == 1

    posted = confirm(client, user, ledger, rule["id"], "2026-10-25", amount=88500, occurred_on="2026-10-26")
    assert posted["occurred_on"] == "2026-10-26" and Decimal(str(posted["amount"])) == Decimal("88500")
    assert posted["kind"] == "income" and posted["description"] == "Зарплата"
    assert prompts(client, user) == []
    assert len(transactions(client, user, ledger, "2026-10")) == 1


def test_skipped_income_is_not_asked_again(client, today):
    user = register_and_login(client, "skipinc@example.com")
    ledger = personal_ledger(client, user)
    rule = make_rule(client, user, ledger, kind="income", name="Подработка", amount=10000, start_on="2026-10-29")
    assert [item["due_on"] for item in prompts(client, user)] == ["2026-10-29"]
    url = f"/finance/ledgers/{ledger}/recurring/{rule['id']}/occurrences/2026-10-29/skip"
    assert client.post(url, headers=user["headers"]).status_code == 204
    assert prompts(client, user) == []
    assert transactions(client, user, ledger, "2026-10") == []


def test_prompts_cover_household_ledger_and_paused_rules_are_quiet(client, today):
    owner = register_and_login(client, "hp-owner@example.com")
    wife = register_and_login(client, "hp-wife@example.com")
    household_id = new_household(client, owner, wife)
    family = household_ledger(client, owner, household_id)
    rule = make_rule(client, owner, family, kind="income", name="Пособие", amount=8000, start_on="2026-10-28")

    # Спрашивают обоих участников; ответ одного закрывает вопрос и для второго
    assert [item["ledger_kind"] for item in prompts(client, wife)] == ["household"]
    confirm(client, wife, family, rule["id"], "2026-10-28")
    assert prompts(client, owner) == []

    other = make_rule(client, owner, family, kind="income", name="Аренда гаража", amount=3000, start_on="2026-10-29")
    client.patch(f"/finance/ledgers/{family}/recurring/{other['id']}", json={"is_active": False}, headers=owner["headers"])
    assert prompts(client, owner) == []


def test_future_start_does_not_post_anything_yet(client, today):
    user = register_and_login(client, "future@example.com")
    ledger = personal_ledger(client, user)
    make_rule(client, user, ledger, kind="income", name="Премия", amount=10000, start_on="2026-12-20")
    assert transactions(client, user, ledger, "2026-12") == []
    assert transactions(client, user, ledger, "2026-10") == []
    assert prompts(client, user) == []


def test_deleting_confirmed_income_marks_it_skipped(client, today):
    user = register_and_login(client, "del@example.com")
    ledger = personal_ledger(client, user)
    rule = make_rule(client, user, ledger, kind="income", name="Аванс", amount=50000, start_on="2026-10-10")
    posted = confirm(client, user, ledger, rule["id"], "2026-10-10")

    response = client.delete(f"/finance/ledgers/{ledger}/transactions/{posted['id']}", headers=user["headers"])
    assert response.status_code == 204

    # Выплата считается пропущенной: заново операция не создаётся и в ожидаемых её нет
    assert transactions(client, user, ledger, "2026-10") == []
    upcoming = client.get(f"/finance/ledgers/{ledger}/upcoming?days=5", headers=user["headers"]).json()
    assert upcoming == []


# ------------------------------------------------------------- периодичность и основные / дополнительные


def test_semimonthly_income_on_two_dates(client, today):
    user = register_and_login(client, "semi@example.com")
    ledger = personal_ledger(client, user)
    rule = make_rule(
        client, user, ledger, kind="income", name="Зарплата", amount=45000,
        frequency="semimonthly", start_on="2026-10-10", day_of_month=10, second_day_of_month=25,
    )
    assert (rule["frequency"], rule["day_of_month"], rule["second_day_of_month"]) == ("semimonthly", 10, 25)
    assert rule["next_due_on"] == "2026-11-10"
    assert Decimal(str(rule["monthly_amount"])) == Decimal("90000")

    upcoming = client.get(f"/finance/ledgers/{ledger}/upcoming?days=30", headers=user["headers"]).json()
    assert [item["due_on"] for item in upcoming] == ["2026-10-10", "2026-10-25", "2026-11-10", "2026-11-25"]

    # Оба дня обязательны и должны различаться; второй день только у «два раза в месяц»
    base = dict(kind="income", frequency="semimonthly", start_on="2026-11-05")
    assert add_rule(client, user, ledger, **base, day_of_month=5).status_code == 422
    assert add_rule(client, user, ledger, **base, day_of_month=5, second_day_of_month=5).status_code == 422
    assert add_rule(client, user, ledger, second_day_of_month=20).status_code == 422

    # Смена частоты на «каждый месяц» убирает второй день
    url = f"/finance/ledgers/{ledger}/recurring/{rule['id']}"
    changed = client.patch(url, json={"frequency": "monthly"}, headers=user["headers"]).json()
    assert changed["second_day_of_month"] is None and changed["day_of_month"] == 10
    # Обратно на «два раза в месяц» без второго дня нельзя
    assert client.patch(url, json={"frequency": "semimonthly"}, headers=user["headers"]).status_code == 422
    both = client.patch(url, json={"frequency": "semimonthly", "second_day_of_month": 20}, headers=user["headers"])
    assert both.status_code == 200 and both.json()["second_day_of_month"] == 20


def test_biweekly_has_no_average_monthly_amount(client, today):
    user = register_and_login(client, "biweekly@example.com")
    ledger = personal_ledger(client, user)
    rule = make_rule(client, user, ledger, kind="income", name="Зарплата", amount=30000, frequency="biweekly", start_on="2026-10-16")
    assert rule["monthly_amount"] is None
    # Нагрузка считает обычный месяц: две выплаты, без пересчёта в среднее
    load = client.get(f"/finance/ledgers/{ledger}/load", headers=user["headers"]).json()
    assert Decimal(str(load["income_monthly"])) == Decimal("60000")


def test_primary_flag_for_incomes_and_payments(client, today):
    user = register_and_login(client, "primary@example.com")
    ledger = personal_ledger(client, user)
    extra = make_rule(client, user, ledger, kind="income", name="Кэшбэк", amount=700, start_on="2026-11-01", is_primary=False)
    subscription = make_rule(client, user, ledger, name="Подписка", amount=300, start_on="2026-11-02", is_primary=False)
    rent = make_rule(client, user, ledger, name="Аренда", amount=35000, start_on="2026-11-03")
    assert extra["is_primary"] is False and subscription["is_primary"] is False and rent["is_primary"] is True

    url = f"/finance/ledgers/{ledger}/recurring/{extra['id']}"
    assert client.patch(url, json={"is_primary": True}, headers=user["headers"]).json()["is_primary"] is True
    assert client.patch(url, json={"is_primary": None}, headers=user["headers"]).status_code == 422

    upcoming = client.get(f"/finance/ledgers/{ledger}/upcoming?days=10", headers=user["headers"]).json()
    assert {item["rule_name"]: item["is_primary"] for item in upcoming} == {
        "Кэшбэк": True,
        "Подписка": False,
        "Аренда": True,
    }


def test_expense_auto_post_still_works(client, today):
    user = register_and_login(client, "autopay@example.com")
    ledger = personal_ledger(client, user)
    make_rule(client, user, ledger, name="Подписка", amount=300, start_on="2026-10-02", auto_post=True)
    for _ in range(2):  # повторные чтения ничего не дублируют
        posted = transactions(client, user, ledger, "2026-10")
        assert [(item["occurred_on"], item["kind"]) for item in posted] == [("2026-10-02", "expense")]


# ------------------------------------------------------------- обязательные платежи


def test_expense_rule_waits_for_confirmation(client, today):
    user = register_and_login(client, "rent@example.com")
    ledger = personal_ledger(client, user)
    rule = make_rule(client, user, ledger, name="Аренда", amount=35000, start_on="2026-10-03")

    assert rule["kind"] == "expense" and rule["auto_post"] is False and rule["is_primary"] is True
    assert rule["category_name"] == "Обязательные платежи"
    assert transactions(client, user, ledger, "2026-10") == []

    upcoming = client.get(f"/finance/ledgers/{ledger}/upcoming?days=30", headers=user["headers"]).json()
    # Просроченное 3 октября и ожидаемое 3 ноября
    assert [(item["due_on"], item["overdue"], item["status"]) for item in upcoming] == [
        ("2026-10-03", True, "pending"),
        ("2026-11-03", False, "pending"),
    ]

    url = f"/finance/ledgers/{ledger}/recurring/{rule['id']}/occurrences/2026-10-03"
    paid = client.post(f"{url}/confirm", headers=user["headers"])
    assert paid.status_code == 201, paid.text
    assert paid.json()["occurred_on"] == "2026-10-03"
    assert Decimal(str(paid.json()["amount"])) == Decimal("35000")
    assert paid.json()["kind"] == "expense"

    # Повторно отметить нельзя
    assert client.post(f"{url}/confirm", headers=user["headers"]).status_code == 409
    assert client.post(f"{url}/skip", headers=user["headers"]).status_code == 409

    upcoming = client.get(f"/finance/ledgers/{ledger}/upcoming?days=30", headers=user["headers"]).json()
    assert [item["due_on"] for item in upcoming] == ["2026-11-03"]
    assert len(transactions(client, user, ledger, "2026-10")) == 1


def test_confirm_with_actual_amount_and_date(client, today):
    user = register_and_login(client, "actual@example.com")
    ledger = personal_ledger(client, user)
    rule = make_rule(client, user, ledger, name="Интернет", amount=800, start_on="2026-11-05")

    url = f"/finance/ledgers/{ledger}/recurring/{rule['id']}/occurrences/2026-11-05/confirm"
    response = client.post(url, json={"amount": 750.5, "occurred_on": "2026-10-28"}, headers=user["headers"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert Decimal(str(body["amount"])) == Decimal("750.50") and body["occurred_on"] == "2026-10-28"


def test_confirm_in_advance_defaults_to_today(client, today):
    user = register_and_login(client, "adv@example.com")
    ledger = personal_ledger(client, user)
    rule = make_rule(client, user, ledger, name="Страховка", amount=5000, start_on="2026-11-15")
    response = client.post(
        f"/finance/ledgers/{ledger}/recurring/{rule['id']}/occurrences/2026-11-15/confirm", headers=user["headers"]
    )
    assert response.status_code == 201
    assert response.json()["occurred_on"] == "2026-10-28"


def test_confirm_rejects_date_without_payment(client, today):
    user = register_and_login(client, "nodate@example.com")
    ledger = personal_ledger(client, user)
    rule = make_rule(client, user, ledger, name="Аренда", amount=35000, start_on="2026-10-03")
    base = f"/finance/ledgers/{ledger}/recurring/{rule['id']}/occurrences"
    # 4 октября платежа нет, 3 сентября правило ещё не действовало
    assert client.post(f"{base}/2026-10-04/confirm", headers=user["headers"]).status_code == 422
    assert client.post(f"{base}/2026-09-03/confirm", headers=user["headers"]).status_code == 422
    assert client.post(f"{base}/2026-10-04/skip", headers=user["headers"]).status_code == 422


def test_skip_and_undo(client, today):
    user = register_and_login(client, "skip@example.com")
    ledger = personal_ledger(client, user)
    rule = make_rule(client, user, ledger, name="Секция", amount=3000, start_on="2026-10-20")
    base = f"/finance/ledgers/{ledger}/recurring/{rule['id']}/occurrences/2026-10-20"

    assert client.post(f"{base}/skip", headers=user["headers"]).status_code == 204
    pending = client.get(f"/finance/ledgers/{ledger}/upcoming?days=5", headers=user["headers"]).json()
    assert pending == []

    # Отмена отметки возвращает выплату в ожидаемые
    assert client.delete(base, headers=user["headers"]).status_code == 204
    pending = client.get(f"/finance/ledgers/{ledger}/upcoming?days=5", headers=user["headers"]).json()
    assert [item["due_on"] for item in pending] == ["2026-10-20"]

    # Отмена оплаченного удаляет и операцию
    assert client.post(f"{base}/confirm", headers=user["headers"]).status_code == 201
    assert len(transactions(client, user, ledger, "2026-10")) == 1
    assert client.delete(base, headers=user["headers"]).status_code == 204
    assert transactions(client, user, ledger, "2026-10") == []

    # Отменять нечего
    assert client.delete(f"/finance/ledgers/{ledger}/recurring/{rule['id']}/occurrences/2026-11-20", headers=user["headers"]).status_code == 404


# ------------------------------------------------------------- изменение и удаление


def test_update_pause_and_delete_rule(client, today):
    user = register_and_login(client, "upd@example.com")
    ledger = personal_ledger(client, user)
    rule = make_rule(client, user, ledger, kind="income", name="Подработка", amount=20000, start_on="2026-10-01")
    confirm(client, user, ledger, rule["id"], "2026-10-01")
    assert len(transactions(client, user, ledger, "2026-10")) == 1
    url = f"/finance/ledgers/{ledger}/recurring/{rule['id']}"

    changed = client.patch(url, json={"amount": 25000, "name": "Подработка (проект)"}, headers=user["headers"])
    assert changed.status_code == 200, changed.text
    assert changed.json()["name"] == "Подработка (проект)"
    assert Decimal(str(changed.json()["amount"])) == Decimal("25000")

    paused = client.patch(url, json={"is_active": False}, headers=user["headers"])
    assert paused.status_code == 200 and paused.json()["is_active"] is False
    assert paused.json()["next_due_on"] is None

    # Пауза не стирает уже полученное
    assert len(transactions(client, user, ledger, "2026-10")) == 1

    assert client.patch(url, json={"name": None}, headers=user["headers"]).status_code == 422
    assert client.delete(url, headers=user["headers"]).status_code == 204
    assert client.delete(url, headers=user["headers"]).status_code == 404
    # Операция осталась обычной операцией
    assert len(transactions(client, user, ledger, "2026-10")) == 1
    assert client.get(f"/finance/ledgers/{ledger}/recurring", headers=user["headers"]).json() == []


def test_changing_frequency_clears_day_of_month(client, today):
    user = register_and_login(client, "freq@example.com")
    ledger = personal_ledger(client, user)
    rule = make_rule(client, user, ledger, name="Кружок", amount=1000, start_on="2026-11-02")
    assert rule["day_of_month"] == 2
    changed = client.patch(
        f"/finance/ledgers/{ledger}/recurring/{rule['id']}", json={"frequency": "weekly"}, headers=user["headers"]
    )
    assert changed.status_code == 200
    assert changed.json()["day_of_month"] is None
    assert changed.json()["frequency"] == "weekly"


def test_validation_errors(client, today):
    user = register_and_login(client, "val@example.com")
    ledger = personal_ledger(client, user)
    assert add_rule(client, user, ledger, amount=0).status_code == 422
    assert add_rule(client, user, ledger, amount=-5).status_code == 422
    assert add_rule(client, user, ledger, name="   ").status_code == 422
    assert add_rule(client, user, ledger, frequency="daily").status_code == 422
    assert add_rule(client, user, ledger, frequency="weekly", day_of_month=5).status_code == 422
    assert add_rule(client, user, ledger, day_of_month=32).status_code == 422
    assert add_rule(client, user, ledger, start_on="2026-11-10", end_on="2026-11-01").status_code == 422
    assert add_rule(client, user, ledger, kind="transfer").status_code == 422


def test_categories_are_checked_and_protected(client, today):
    user = register_and_login(client, "cat@example.com")
    other = register_and_login(client, "cat2@example.com")
    ledger = personal_ledger(client, user)
    other_ledger = personal_ledger(client, other)

    categories = client.get(f"/finance/ledgers/{ledger}/categories", headers=user["headers"]).json()
    income_category = next(c["id"] for c in categories if c["kind"] == "income")
    expense_category = next(c["id"] for c in categories if c["name"] == "Жильё и коммунальные")
    foreign_category = client.get(f"/finance/ledgers/{other_ledger}/categories", headers=other["headers"]).json()[0]["id"]

    # Категория другого типа и чужая категория не подходят
    assert add_rule(client, user, ledger, category_id=income_category).status_code == 422
    assert add_rule(client, user, ledger, category_id=foreign_category).status_code == 422

    rule = make_rule(client, user, ledger, name="ЖКХ", amount=6000, category_id=expense_category)
    assert rule["category_name"] == "Жильё и коммунальные"

    # Категорию, на которую ссылается правило, удалить нельзя
    response = client.delete(f"/finance/ledgers/{ledger}/categories/{expense_category}", headers=user["headers"])
    assert response.status_code == 409


# ------------------------------------------------------------- права в семейной книге


def test_household_permissions(client, today):
    owner = register_and_login(client, "ho@example.com", "Даня")
    wife = register_and_login(client, "hw@example.com", "Леся")
    friend = register_and_login(client, "hf@example.com", "Друг")
    outsider = register_and_login(client, "hx@example.com", "Чужой")
    household_id = new_household(client, owner, wife, friend)
    ledger = household_ledger(client, owner, household_id)

    # Любой участник может добавить платёж
    rule = make_rule(client, wife, ledger, name="Садик", amount=9000, start_on="2026-11-05")
    assert rule["can_edit"] is True
    url = f"/finance/ledgers/{ledger}/recurring/{rule['id']}"

    # Другой обычный участник видит правило, но менять его не может
    listing = client.get(f"/finance/ledgers/{ledger}/recurring", headers=friend["headers"]).json()
    assert [(item["id"], item["can_edit"]) for item in listing] == [(rule["id"], False)]
    assert client.patch(url, json={"amount": 1}, headers=friend["headers"]).status_code == 403
    assert client.delete(url, headers=friend["headers"]).status_code == 403

    # Владелец семьи управляет любыми правилами
    assert client.patch(url, json={"amount": 9500}, headers=owner["headers"]).status_code == 200
    # Отметить оплату может любой участник
    paid = client.post(f"{url}/occurrences/2026-11-05/confirm", headers=friend["headers"])
    assert paid.status_code == 201 and paid.json()["created_by_name"] == "Друг"
    # Отменить отметку с чужой операцией обычный участник не может, владелец может
    other_paid = client.post(f"{url}/occurrences/2026-12-05/confirm", headers=wife["headers"])
    assert other_paid.status_code == 201
    assert client.delete(f"{url}/occurrences/2026-12-05", headers=friend["headers"]).status_code == 403
    assert client.delete(f"{url}/occurrences/2026-12-05", headers=owner["headers"]).status_code == 204

    # Посторонний не видит книгу вообще
    assert client.get(f"/finance/ledgers/{ledger}/recurring", headers=outsider["headers"]).status_code == 404
    assert add_rule(client, outsider, ledger).status_code == 404
    assert client.delete(url, headers=owner["headers"]).status_code == 204


def test_other_users_ledger_is_not_accessible(client, today):
    user = register_and_login(client, "mine@example.com")
    stranger = register_and_login(client, "theirs@example.com")
    ledger = personal_ledger(client, user)
    rule = make_rule(client, user, ledger, name="Мой платёж")
    base = f"/finance/ledgers/{ledger}"
    assert client.get(f"{base}/recurring", headers=stranger["headers"]).status_code == 404
    assert client.patch(f"{base}/recurring/{rule['id']}", json={"amount": 1}, headers=stranger["headers"]).status_code == 404
    assert client.get(f"{base}/upcoming", headers=stranger["headers"]).status_code == 404
    assert client.get(f"{base}/cycles", headers=stranger["headers"]).status_code == 404
    assert client.get(f"{base}/load", headers=stranger["headers"]).status_code == 404
    assert client.get(f"{base}/goals", headers=stranger["headers"]).status_code == 404
    assert client.get(f"{base}/recurring").status_code == 401


def test_rule_from_another_ledger_is_not_found(client, today):
    user = register_and_login(client, "a@example.com")
    friend = register_and_login(client, "b@example.com")
    ledger_a = personal_ledger(client, user)
    ledger_b = personal_ledger(client, friend)
    rule = make_rule(client, user, ledger_a, name="Платёж")
    # Своя книга, но id правила чужой книги
    response = client.patch(
        f"/finance/ledgers/{ledger_b}/recurring/{rule['id']}", json={"amount": 5}, headers=friend["headers"]
    )
    assert response.status_code == 404
    confirm = client.post(
        f"/finance/ledgers/{ledger_b}/recurring/{rule['id']}/occurrences/2026-11-01/confirm", headers=friend["headers"]
    )
    assert confirm.status_code == 404
