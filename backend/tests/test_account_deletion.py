"""Удаление аккаунта: пароль, чистка данных, судьба семей, фото и сессии."""

from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import (
    Base,
    FinanceTransaction,
    FinancialGoal,
    Food,
    Household,
    HouseholdMember,
    Ledger,
    ProgressPhoto,
    RefreshToken,
    User,
)
from tests.photo_samples import JPEG_PLAIN
from tests.helpers import new_household, register_and_login

PASSWORD = "very-strong-password-123"


def delete_account(client, user, password: str = PASSWORD):
    return client.post("/auth/delete-account", json={"password": password}, headers=user["headers"])


def make_ledger(client, user, kind="personal", household_id=None):
    body = {"kind": kind, "currency": "RUB"}
    if household_id:
        body["household_id"] = household_id
    response = client.post("/finance/ledgers", json=body, headers=user["headers"])
    assert response.status_code == 201, response.text
    return response.json()


def add_tx(client, user, ledger_id, amount=100, day="2026-10-10", category="Продукты"):
    categories = client.get(f"/finance/ledgers/{ledger_id}/categories", headers=user["headers"]).json()
    category_id = next(item["id"] for item in categories if item["name"] == category)
    response = client.post(
        f"/finance/ledgers/{ledger_id}/transactions",
        json={"category_id": category_id, "amount": amount, "occurred_on": day},
        headers=user["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_wrong_password_keeps_account(client):
    user = register_and_login(client, "keep@example.com")
    response = delete_account(client, user, "wrong-password-123456")
    assert response.status_code == 403
    assert client.get("/users/me", headers=user["headers"]).status_code == 200


def test_password_attempts_are_limited(client):
    user = register_and_login(client, "limit@example.com")
    for _ in range(5):
        assert delete_account(client, user, "wrong-password-123456").status_code == 403
    # Шестая попытка блокируется, даже если пароль верный
    assert delete_account(client, user).status_code == 429


def test_delete_requires_authentication(client):
    response = client.post("/auth/delete-account", json={"password": PASSWORD})
    assert response.status_code == 401


def test_deleted_user_cannot_use_token_or_login_and_email_is_free(client):
    user = register_and_login(client, "gone@example.com", "Gone")
    response = delete_account(client, user)
    assert response.status_code == 204
    # Cookie сессии удалена
    assert "refresh_token" in response.headers.get("set-cookie", "")

    assert client.get("/users/me", headers=user["headers"]).status_code == 401
    login = client.post("/auth/login", json={"email": "gone@example.com", "password": PASSWORD})
    assert login.status_code == 401

    # Тот же email можно зарегистрировать снова, это новый человек без старых данных
    again = register_and_login(client, "gone@example.com", "Gone again")
    assert again["id"] != user["id"]


def test_personal_data_is_removed(client, engine):
    user = register_and_login(client, "wipe@example.com", "Wipe")
    other = register_and_login(client, "stay@example.com", "Stay")
    headers = user["headers"]

    # Вес, цель по весу, финансы, личный продукт
    assert client.post(
        f"/users/{user['id']}/weight-records",
        json={"measurement_date": "2026-10-20", "weight_kg": 80},
        headers=headers,
    ).status_code == 201
    ledger = make_ledger(client, user)
    add_tx(client, user, ledger["id"])
    client.post(
        f"/finance/ledgers/{ledger['id']}/goals",
        json={"kind": "savings", "name": "Отпуск", "target_amount": 1000},
        headers=headers,
    )
    other_ledger = make_ledger(client, other)
    add_tx(client, other, other_ledger["id"])

    preview = client.get("/auth/delete-account/preview", headers=headers).json()
    assert preview["counts"]["weight_records"] == 1
    assert preview["counts"]["finance_transactions"] == 1
    assert preview["households_to_delete"] == [] and preview["households_to_leave"] == []

    assert delete_account(client, user).status_code == 204

    with Session(engine) as db:
        assert db.get(User, user["id"]) is None
        assert db.scalar(select(func.count()).select_from(Ledger).where(Ledger.user_id == user["id"])) == 0
        assert db.scalar(select(func.count()).select_from(FinancialGoal)) == 0
        assert db.scalar(select(func.count()).select_from(RefreshToken).where(RefreshToken.user_id == user["id"])) == 0
        # Данные другого пользователя на месте
        assert db.scalar(select(func.count()).select_from(FinanceTransaction)) == 1
        assert db.get(User, other["id"]) is not None


def test_no_table_keeps_rows_pointing_at_deleted_user(client, engine):
    """Защита от будущих ошибок: после удаления ни одна таблица не ссылается на несуществующего пользователя.

    Если добавить новую таблицу со ссылкой на users и забыть про удаление аккаунта, этот тест подскажет.
    """
    user = register_and_login(client, "full@example.com", "Full")
    friend = register_and_login(client, "friend@example.com", "Friend")
    household_id = new_household(client, user, friend, name="Дом")
    ledger = make_ledger(client, user)
    add_tx(client, user, ledger["id"])
    shared = make_ledger(client, user, "household", household_id)
    add_tx(client, user, shared["id"])
    assert client.post("/foods", json={
        "name": "Моя гречка", "category": "grains", "calories_per_100g": 340,
        "protein_per_100g": 12, "fat_per_100g": 3, "carbs_per_100g": 68,
    }, headers=user["headers"]).status_code == 201

    assert delete_account(client, user).status_code == 204

    with Session(engine) as db:
        problems = []
        for table in Base.metadata.sorted_tables:
            for fk in table.foreign_keys:
                if fk.column.table.name != "users":
                    continue
                count = db.execute(
                    select(func.count()).select_from(table).where(table.c[fk.parent.name] == user["id"])
                ).scalar()
                if count:
                    problems.append((table.name, fk.parent.name, count))
        assert problems == []


def test_sole_member_household_is_deleted_with_its_ledger(client, engine):
    user = register_and_login(client, "solo@example.com")
    household_id = new_household(client, user, name="Одиночка")
    shared = make_ledger(client, user, "household", household_id)
    add_tx(client, user, shared["id"])

    preview = client.get("/auth/delete-account/preview", headers=user["headers"]).json()
    assert preview["households_to_delete"] == [{"id": household_id, "name": "Одиночка"}]
    assert preview["counts"]["finance_transactions"] == 1

    assert delete_account(client, user).status_code == 204
    with Session(engine) as db:
        assert db.get(Household, household_id) is None
        assert db.scalar(select(func.count()).select_from(Ledger)) == 0
        assert db.scalar(select(func.count()).select_from(FinanceTransaction)) == 0


def test_owner_leaves_and_ownership_passes_to_oldest_admin_or_member(client, engine):
    owner = register_and_login(client, "owner@example.com", "Даня")
    wife = register_and_login(client, "wife@example.com", "Леся")
    household_id = new_household(client, owner, wife, name="Семья")
    shared = make_ledger(client, owner, "household", household_id)
    tx = add_tx(client, owner, shared["id"], amount=500)

    preview = client.get("/auth/delete-account/preview", headers=owner["headers"]).json()
    assert preview["households_to_leave"] == [{"id": household_id, "name": "Семья", "new_owner_name": "Леся"}]

    assert delete_account(client, owner).status_code == 204

    with Session(engine) as db:
        assert db.get(Household, household_id) is not None
        member = db.get(HouseholdMember, (household_id, wife["id"]))
        assert member.role == "owner"

    # Общая операция осталась в семейной книге с подписью удалённого автора
    listing = client.get(
        f"/finance/ledgers/{shared['id']}/transactions?month=2026-10", headers=wife["headers"]
    ).json()
    assert [(item["id"], item["created_by_user_id"], item["created_by_name"]) for item in listing] == [
        (tx["id"], None, "Удалённый пользователь")
    ]


def test_admin_is_preferred_as_new_owner(client, engine):
    owner = register_and_login(client, "o@example.com", "Owner")
    member = register_and_login(client, "m@example.com", "Member")
    admin = register_and_login(client, "a@example.com", "Admin")
    household_id = new_household(client, owner, member, admin, name="Команда")
    assert client.patch(
        f"/households/{household_id}/members/{admin['id']}",
        json={"role": "admin"},
        headers=owner["headers"],
    ).status_code == 200

    assert delete_account(client, owner).status_code == 204
    with Session(engine) as db:
        assert db.get(HouseholdMember, (household_id, admin["id"])).role == "owner"
        assert db.get(HouseholdMember, (household_id, member["id"])).role == "member"


def test_regular_member_just_leaves_household(client, engine):
    owner = register_and_login(client, "o2@example.com", "Owner")
    member = register_and_login(client, "m2@example.com", "Member")
    household_id = new_household(client, owner, member)
    assert delete_account(client, member).status_code == 204
    with Session(engine) as db:
        assert db.get(HouseholdMember, (household_id, member["id"])) is None
        assert db.get(HouseholdMember, (household_id, owner["id"])).role == "owner"


def test_shared_foods_stay_with_household(client, engine):
    owner = register_and_login(client, "fo@example.com", "Owner")
    member = register_and_login(client, "fm@example.com", "Member")
    household_id = new_household(client, owner, member)
    created = client.post("/foods", json={
        "name": "Семейный творог", "category": "dairy", "calories_per_100g": 120,
        "protein_per_100g": 18, "fat_per_100g": 4, "carbs_per_100g": 3, "household_id": household_id,
    }, headers=member["headers"])
    assert created.status_code == 201, created.text

    assert delete_account(client, member).status_code == 204
    with Session(engine) as db:
        food = db.scalar(select(Food).where(Food.name == "Семейный творог"))
        assert food is not None and food.owner_user_id is None and food.household_id == household_id


def test_progress_photo_files_are_removed(client, engine, upload_dir):
    user = register_and_login(client, "photo@example.com")
    response = client.post(
        f"/users/{user['id']}/progress-photos",
        params={"taken_on": date.today().isoformat()},
        content=JPEG_PLAIN,
        headers={**user["headers"], "Content-Type": "image/jpeg"},
    )
    assert response.status_code == 201, response.text
    files = [path for path in Path(upload_dir).rglob("*") if path.is_file()]
    assert len(files) == 1

    assert delete_account(client, user).status_code == 204
    assert [path for path in Path(upload_dir).rglob("*") if path.is_file()] == []
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ProgressPhoto)) == 0


def test_invites_created_by_deleted_user_are_removed(client, engine):
    owner = register_and_login(client, "inv-o@example.com")
    member = register_and_login(client, "inv-m@example.com")
    household_id = new_household(client, owner, member)
    # Владелец создаёт ещё один неиспользованный код
    assert client.post(f"/households/{household_id}/invites", headers=owner["headers"]).status_code == 201
    assert delete_account(client, owner).status_code == 204
    # Новый владелец (member) видит свои приглашения, старых кодов бывшего владельца нет
    listing = client.get(f"/households/{household_id}/invites", headers=member["headers"])
    assert listing.status_code == 200
    assert listing.json() == []
