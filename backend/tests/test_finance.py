from decimal import Decimal

from tests.helpers import register_and_login


def create_personal_ledger(client, user, currency: str = "EUR") -> dict:
    """Создаёт личную книгу пользователя и возвращает её данные.

    Результат, например: {"id": 1, "kind": "personal", "currency": "EUR", "can_manage": True, ...}
    """
    response = client.post(
        "/finance/ledgers",
        json={"kind": "personal", "currency": currency},
        headers=user["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_household(client, owner, member) -> int:
    """Создаёт домохозяйство «Семья» с владельцем owner и участником member; возвращает его id."""
    response = client.post("/households", json={"name": "Семья"}, headers=owner["headers"])
    assert response.status_code == 201, response.text
    household_id = response.json()["id"]

    response = client.post(
        f"/households/{household_id}/members",
        json={"user_id": member["id"]},
        headers=owner["headers"],
    )
    assert response.status_code == 201, response.text
    return household_id


def create_household_ledger(client, user, household_id: int):
    """Пытается создать семейную книгу; возвращает ответ сервера без проверок."""
    return client.post(
        "/finance/ledgers",
        json={"kind": "household", "household_id": household_id, "currency": "EUR"},
        headers=user["headers"],
    )


def category_id(client, user, ledger_id: int, name: str) -> int:
    """Находит id категории книги по названию, например "Продукты"."""
    response = client.get(f"/finance/ledgers/{ledger_id}/categories", headers=user["headers"])
    assert response.status_code == 200, response.text
    return next(item["id"] for item in response.json() if item["name"] == name)


def add_transaction(client, user, ledger_id, cat_id, amount, day, description=None) -> dict:
    """Добавляет операцию; amount — число, day — "2026-10-10"."""
    response = client.post(
        f"/finance/ledgers/{ledger_id}/transactions",
        json={"category_id": cat_id, "amount": amount, "occurred_on": day, "description": description},
        headers=user["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_personal_ledger_seeds_categories(client):
    user = register_and_login(client, "fin@example.com", "Fin")
    ledger = create_personal_ledger(client, user)

    assert ledger["kind"] == "personal"
    assert ledger["currency"] == "EUR"
    assert ledger["household_id"] is None
    assert ledger["can_manage"] is True

    response = client.get(f"/finance/ledgers/{ledger['id']}/categories", headers=user["headers"])
    pairs = {(item["kind"], item["name"]) for item in response.json()}
    assert ("expense", "Продукты") in pairs
    assert ("income", "Зарплата") in pairs

    # Вторая личная книга того же пользователя не создаётся
    again = client.post(
        "/finance/ledgers",
        json={"kind": "personal", "currency": "EUR"},
        headers=user["headers"],
    )
    assert again.status_code == 409

    listing = client.get("/finance/ledgers", headers=user["headers"])
    assert [item["id"] for item in listing.json()] == [ledger["id"]]


def test_personal_ledger_is_private(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    other = register_and_login(client, "other@example.com", "Other")
    ledger = create_personal_ledger(client, owner)

    # Для другого пользователя книги «не существует» во всех разделах
    for path in ("categories", "transactions?month=2026-10", "summary?month=2026-10"):
        response = client.get(f"/finance/ledgers/{ledger['id']}/{path}", headers=other["headers"])
        assert response.status_code == 404, path

    assert client.get("/finance/ledgers", headers=other["headers"]).json() == []


def test_household_ledger_permissions(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    member = register_and_login(client, "member@example.com", "Member")
    outsider = register_and_login(client, "outsider@example.com", "Outsider")
    household_id = make_household(client, owner, member)

    # Обычный участник создавать семейную книгу не может; посторонний не видит домохозяйство
    assert create_household_ledger(client, member, household_id).status_code == 403
    assert create_household_ledger(client, outsider, household_id).status_code == 404

    response = create_household_ledger(client, owner, household_id)
    assert response.status_code == 201, response.text
    ledger = response.json()
    assert ledger["kind"] == "household"
    assert ledger["household_name"] == "Семья"

    # Повторное создание: 409
    assert create_household_ledger(client, owner, household_id).status_code == 409

    # Участник видит книгу, но управлять ею не может
    listing = client.get("/finance/ledgers", headers=member["headers"]).json()
    assert len(listing) == 1 and listing[0]["can_manage"] is False

    # Посторонний книгу не видит
    response = client.get(f"/finance/ledgers/{ledger['id']}/categories", headers=outsider["headers"])
    assert response.status_code == 404

    # Участник вносит операцию, владелец видит её вместе с именем автора
    food = category_id(client, member, ledger["id"], "Продукты")
    add_transaction(client, member, ledger["id"], food, 15, "2026-10-12")
    response = client.get(
        f"/finance/ledgers/{ledger['id']}/transactions",
        params={"month": "2026-10"},
        headers=owner["headers"],
    )
    assert [item["created_by_name"] for item in response.json()] == ["Member"]


def test_transactions_and_summary(client):
    user = register_and_login(client, "fin@example.com", "Fin")
    ledger = create_personal_ledger(client, user)
    lid = ledger["id"]
    salary = category_id(client, user, lid, "Зарплата")
    food = category_id(client, user, lid, "Продукты")

    add_transaction(client, user, lid, salary, 1000, "2026-10-05")
    add_transaction(client, user, lid, food, 120.5, "2026-10-10", "Супермаркет")
    add_transaction(client, user, lid, food, 30, "2026-11-02")

    # В октябре две операции, новые первыми; ноябрьская не попадает
    october = client.get(
        f"/finance/ledgers/{lid}/transactions",
        params={"month": "2026-10"},
        headers=user["headers"],
    ).json()
    assert [item["description"] for item in october] == ["Супермаркет", None]
    assert Decimal(october[0]["amount"]) == Decimal("120.50")
    assert october[0]["kind"] == "expense"

    summary = client.get(
        f"/finance/ledgers/{lid}/summary",
        params={"month": "2026-10"},
        headers=user["headers"],
    ).json()
    assert summary["currency"] == "EUR"
    assert Decimal(summary["income"]) == Decimal("1000")
    assert Decimal(summary["expense"]) == Decimal("120.5")
    assert Decimal(summary["balance"]) == Decimal("879.5")

    food_row = next(row for row in summary["categories"] if row["name"] == "Продукты")
    assert Decimal(food_row["total"]) == Decimal("120.5")

    november = client.get(
        f"/finance/ledgers/{lid}/summary",
        params={"month": "2026-11"},
        headers=user["headers"],
    ).json()
    assert Decimal(november["expense"]) == Decimal("30")


def test_budget_appears_in_summary(client):
    user = register_and_login(client, "fin@example.com", "Fin")
    lid = create_personal_ledger(client, user)["id"]
    food = category_id(client, user, lid, "Продукты")
    salary = category_id(client, user, lid, "Зарплата")
    url = f"/finance/ledgers/{lid}/budgets/{food}"
    summary_url = f"/finance/ledgers/{lid}/summary"

    def food_limit():
        rows = client.get(summary_url, params={"month": "2026-10"}, headers=user["headers"]).json()
        return next(row for row in rows["categories"] if row["name"] == "Продукты")["budget_limit"]

    assert food_limit() is None

    assert client.put(url, json={"monthly_limit": 200}, headers=user["headers"]).status_code == 204
    assert Decimal(food_limit()) == Decimal("200")

    # null убирает лимит
    assert client.put(url, json={"monthly_limit": None}, headers=user["headers"]).status_code == 204
    assert food_limit() is None

    # Для категории доходов лимит задать нельзя
    response = client.put(
        f"/finance/ledgers/{lid}/budgets/{salary}",
        json={"monthly_limit": 100},
        headers=user["headers"],
    )
    assert response.status_code == 422


def test_delete_transaction_permissions(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    member = register_and_login(client, "member@example.com", "Member")
    household_id = make_household(client, owner, member)
    lid = create_household_ledger(client, owner, household_id).json()["id"]
    food = category_id(client, owner, lid, "Продукты")

    owner_tx = add_transaction(client, owner, lid, food, 10, "2026-10-10")
    member_tx1 = add_transaction(client, member, lid, food, 20, "2026-10-11")
    member_tx2 = add_transaction(client, member, lid, food, 30, "2026-10-12")

    def delete(user, tx):
        return client.delete(
            f"/finance/ledgers/{lid}/transactions/{tx['id']}", headers=user["headers"]
        )

    # Свою операцию участник удаляет, чужую нет
    assert delete(member, member_tx1).status_code == 204
    assert delete(member, owner_tx).status_code == 403
    # Владелец может удалить операцию участника
    assert delete(owner, member_tx2).status_code == 204
    assert delete(owner, member_tx2).status_code == 404


def test_category_rules(client):
    user = register_and_login(client, "fin@example.com", "Fin")
    lid = create_personal_ledger(client, user)["id"]
    url = f"/finance/ledgers/{lid}/categories"

    response = client.post(url, json={"name": "Подарки", "kind": "expense"}, headers=user["headers"])
    assert response.status_code == 201, response.text
    gifts = response.json()["id"]

    # Дубликат и пустое название отклоняются
    assert client.post(url, json={"name": "Подарки", "kind": "expense"}, headers=user["headers"]).status_code == 409
    assert client.post(url, json={"name": "   ", "kind": "expense"}, headers=user["headers"]).status_code == 422

    # Пустую категорию можно удалить, категорию с операциями нет
    assert client.delete(f"{url}/{gifts}", headers=user["headers"]).status_code == 204
    food = category_id(client, user, lid, "Продукты")
    add_transaction(client, user, lid, food, 5, "2026-10-10")
    assert client.delete(f"{url}/{food}", headers=user["headers"]).status_code == 409


def test_transaction_validation(client):
    user = register_and_login(client, "fin@example.com", "Fin")
    other = register_and_login(client, "other@example.com", "Other")
    lid = create_personal_ledger(client, user)["id"]
    other_lid = create_personal_ledger(client, other)["id"]
    food = category_id(client, user, lid, "Продукты")
    foreign_food = category_id(client, other, other_lid, "Продукты")
    url = f"/finance/ledgers/{lid}/transactions"

    def post(category, amount):
        return client.post(
            url,
            json={"category_id": category, "amount": amount, "occurred_on": "2026-10-10"},
            headers=user["headers"],
        )

    # Нулевая и отрицательная суммы отклоняются
    assert post(food, 0).status_code == 422
    assert post(food, -5).status_code == 422
    # Категория из чужой книги не подходит
    assert post(foreign_food, 10).status_code == 404