import pytest

from tests.helpers import register_and_login


@pytest.fixture()
def household_setup(client):
    """Готовит сцену: владелец, обычный участник, посторонний и одно домохозяйство."""

    # Каждый вызов возвращает словарь вида
    # {"id": 1, "headers": {"Authorization": "Bearer eyJhbGciOi..."}}
    owner = register_and_login(client, "owner@example.com", "Owner")           # id 1
    member = register_and_login(client, "member@example.com", "Member")        # id 2
    outsider = register_and_login(client, "outsider@example.com", "Outsider")  # id 3

    # Владелец создаёт домохозяйство
    response = client.post(
        "/households",
        json={"name": "Дом"},
        headers=owner["headers"],
    )
    assert response.status_code == 201, response.text
    # response.json() → {"id": 1, "name": "Дом", "created_at": "2026-10-22T..."}
    household_id = response.json()["id"]  # 1

    # Владелец добавляет member в домохозяйство
    response = client.post(
        f"/households/{household_id}/members",
        json={"user_id": member["id"]},  # → {"user_id": 2}
        headers=owner["headers"],
    )
    assert response.status_code == 201, response.text
    # response.json() → {"household_id": 1, "user_id": 2, "role": "member",
    #                    "joined_at": "2026-10-22T..."}

    # Всё нужное тестам отдаём одним словарём
    return {
        "household_id": household_id,  # 1
        "owner": owner,
        "member": member,
        "outsider": outsider,
    }


# ---------- Создание домохозяйства ----------

def test_create_household_takes_owner_from_token(client):
    owner = register_and_login(client, "owner@example.com")  # {"id": 1, "headers": {...}}

    response = client.post(
        "/households",
        json={"name": "Дом"},  # owner_user_id больше не нужен
        headers=owner["headers"],
    )
    assert response.status_code == 201, response.text
    household_id = response.json()["id"]  # 1

    response = client.get(
        f"/households/{household_id}/members",
        headers=owner["headers"],
    )
    assert response.status_code == 200
    members = response.json()
    # members → [{"household_id": 1, "user_id": 1, "role": "owner", "joined_at": "..."}]
    assert len(members) == 1
    assert members[0]["user_id"] == owner["id"]  # 1 == 1
    assert members[0]["role"] == "owner"


def test_create_household_requires_token(client):
    response = client.post("/households", json={"name": "Дом"})
    assert response.status_code == 401


def test_create_household_ignores_owner_user_id_from_body(client):
    attacker = register_and_login(client, "attacker@example.com", "Attacker")  # id 1
    victim = register_and_login(client, "victim@example.com", "Victim")        # id 2

    # Злоумышленник пытается назначить владельцем чужой id
    response = client.post(
        "/households",
        json={"name": "Чужой дом", "owner_user_id": victim["id"]},
        # → {"name": "Чужой дом", "owner_user_id": 2}
        headers=attacker["headers"],
    )
    assert response.status_code == 201, response.text
    household_id = response.json()["id"]  # 1

    response = client.get(
        f"/households/{household_id}/members",
        headers=attacker["headers"],
    )
    members = response.json()
    # members → [{"household_id": 1, "user_id": 1, "role": "owner", ...}]
    # user_id равен id злоумышленника (1), а не жертвы (2)
    assert len(members) == 1
    assert members[0]["user_id"] == attacker["id"]
    assert members[0]["role"] == "owner"

    # Жертва доступа к этому домохозяйству не получила
    response = client.get(
        f"/households/{household_id}/members",
        headers=victim["headers"],
    )
    assert response.status_code == 403


# ---------- Просмотр списка участников ----------

def test_members_list_requires_token(client, household_setup):
    household_id = household_setup["household_id"]  # 1

    response = client.get(f"/households/{household_id}/members")
    assert response.status_code == 401


def test_members_list_rejects_invalid_token(client, household_setup):
    household_id = household_setup["household_id"]  # 1

    response = client.get(
        f"/households/{household_id}/members",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401


def test_owner_and_member_can_list_members(client, household_setup):
    household_id = household_setup["household_id"]  # 1
    owner = household_setup["owner"]    # {"id": 1, "headers": {...}}
    member = household_setup["member"]  # {"id": 2, "headers": {...}}

    # Цикл по очереди берёт owner, затем member; переменная user по очереди
    # равна одному из этих словарей
    for user in (owner, member):
        response = client.get(
            f"/households/{household_id}/members",
            headers=user["headers"],
        )
        assert response.status_code == 200, response.text
        # response.json() → [
        #   {"household_id": 1, "user_id": 1, "role": "owner", "joined_at": "..."},
        #   {"household_id": 1, "user_id": 2, "role": "member", "joined_at": "..."},
        # ]
        roles = {item["user_id"]: item["role"] for item in response.json()}
        # roles → {1: "owner", 2: "member"}  (user_id → роль)
        assert roles == {owner["id"]: "owner", member["id"]: "member"}


def test_outsider_cannot_list_members(client, household_setup):
    household_id = household_setup["household_id"]  # 1
    outsider = household_setup["outsider"]          # {"id": 3, "headers": {...}}

    response = client.get(
        f"/households/{household_id}/members",
        headers=outsider["headers"],
    )
    assert response.status_code == 403


def test_list_members_of_unknown_household_returns_404(client, household_setup):
    owner = household_setup["owner"]  # {"id": 1, "headers": {...}}

    # Домохозяйства с id 999999 нет
    response = client.get("/households/999999/members", headers=owner["headers"])
    assert response.status_code == 404


# ---------- Добавление участников ----------

def test_add_member_requires_token(client, household_setup):
    household_id = household_setup["household_id"]  # 1
    newbie = register_and_login(client, "newbie@example.com", "Newbie")  # id 4

    response = client.post(
        f"/households/{household_id}/members",
        json={"user_id": newbie["id"]},  # → {"user_id": 4}
    )
    assert response.status_code == 401


def test_owner_can_add_member(client, household_setup):
    household_id = household_setup["household_id"]  # 1
    owner = household_setup["owner"]                # {"id": 1, "headers": {...}}
    newbie = register_and_login(client, "newbie@example.com", "Newbie")  # id 4

    response = client.post(
        f"/households/{household_id}/members",
        json={"user_id": newbie["id"]},  # → {"user_id": 4}
        headers=owner["headers"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    # body → {"household_id": 1, "user_id": 4, "role": "member", "joined_at": "..."}
    assert body["user_id"] == newbie["id"]
    assert body["role"] == "member"

    # Новый участник теперь видит список; в нём 3 человека: owner, member, newbie
    response = client.get(
        f"/households/{household_id}/members",
        headers=newbie["headers"],
    )
    assert response.status_code == 200
    assert len(response.json()) == 3


def test_regular_member_cannot_add_members(client, household_setup):
    household_id = household_setup["household_id"]  # 1
    owner = household_setup["owner"]                # {"id": 1, "headers": {...}}
    member = household_setup["member"]              # {"id": 2, "headers": {...}}
    newbie = register_and_login(client, "newbie@example.com", "Newbie")  # id 4

    # Обычный участник пытается добавить newbie
    response = client.post(
        f"/households/{household_id}/members",
        json={"user_id": newbie["id"]},
        headers=member["headers"],
    )
    assert response.status_code == 403

    # Проверяем, что newbie действительно не добавился: по-прежнему 2 участника
    response = client.get(
        f"/households/{household_id}/members",
        headers=owner["headers"],
    )
    assert len(response.json()) == 2


def test_outsider_cannot_add_members(client, household_setup):
    household_id = household_setup["household_id"]  # 1
    owner = household_setup["owner"]                # {"id": 1, "headers": {...}}
    outsider = household_setup["outsider"]          # {"id": 3, "headers": {...}}

    # Посторонний пытается добавить в чужое домохозяйство самого себя
    response = client.post(
        f"/households/{household_id}/members",
        json={"user_id": outsider["id"]},  # → {"user_id": 3}
        headers=outsider["headers"],
    )
    assert response.status_code == 403

    # Список участников не изменился
    response = client.get(
        f"/households/{household_id}/members",
        headers=owner["headers"],
    )
    assert len(response.json()) == 2


def test_add_member_to_unknown_household_returns_404(client, household_setup):
    owner = household_setup["owner"]    # {"id": 1, "headers": {...}}
    member = household_setup["member"]  # {"id": 2, "headers": {...}}

    response = client.post(
        "/households/999999/members",
        json={"user_id": member["id"]},
        headers=owner["headers"],
    )
    assert response.status_code == 404


def test_add_unknown_user_returns_404(client, household_setup):
    household_id = household_setup["household_id"]  # 1
    owner = household_setup["owner"]                # {"id": 1, "headers": {...}}

    # Пользователя с id 999999 нет
    response = client.post(
        f"/households/{household_id}/members",
        json={"user_id": 999999},
        headers=owner["headers"],
    )
    assert response.status_code == 404


def test_add_existing_member_returns_409(client, household_setup):
    household_id = household_setup["household_id"]  # 1
    owner = household_setup["owner"]                # {"id": 1, "headers": {...}}
    member = household_setup["member"]              # {"id": 2, "headers": {...}}

    # member уже состоит в домохозяйству (его добавила фикстура)
    response = client.post(
        f"/households/{household_id}/members",
        json={"user_id": member["id"]},  # → {"user_id": 2}
        headers=owner["headers"],
    )
    assert response.status_code == 409


# ---------- Список моих домохозяйств ----------

def test_list_my_households_requires_token(client):
    """Без токена список недоступен: ожидаем 401."""
    response = client.get("/households")
    assert response.status_code == 401


def test_list_my_households_is_empty_for_new_user(client):
    """У нового пользователя домохозяйств нет: ответом должен быть пустой список."""
    # user → {"id": 1, "headers": {...}}
    user = register_and_login(client, "solo@example.com", "Solo")

    response = client.get("/households", headers=user["headers"])

    assert response.status_code == 200, response.text
    # Именно [], а не ошибка и не None: интерфейс может безопасно перебирать список
    assert response.json() == []


def test_list_my_households_shows_role(client, household_setup):
    """Владелец и участник видят домохозяйство со своей ролью, посторонний не видит ничего."""
    household_id = household_setup["household_id"]  # 1
    owner = household_setup["owner"]        # {"id": 1, "headers": {...}}
    member = household_setup["member"]      # {"id": 2, "headers": {...}}
    outsider = household_setup["outsider"]  # {"id": 3, "headers": {...}}

    # Список пар «пользователь, ожидаемая роль»:
    # [(owner, "owner"), (member, "member")]
    expected = [(owner, "owner"), (member, "member")]

    # В каждом проходе цикла кортеж распаковывается на две переменные:
    # сначала user = owner, expected_role = "owner",
    # затем user = member, expected_role = "member".
    for user, expected_role in expected:
        response = client.get("/households", headers=user["headers"])
        assert response.status_code == 200, response.text

        # items → [{"id": 1, "name": "Дом", "created_at": "...", "role": "owner"}]
        items = response.json()
        assert len(items) == 1
        assert items[0]["id"] == household_id
        assert items[0]["name"] == "Дом"
        assert items[0]["role"] == expected_role

    # Посторонний ни в одном домохозяйстве не состоит, поэтому список пуст
    response = client.get("/households", headers=outsider["headers"])
    assert response.status_code == 200
    assert response.json() == []


def test_list_my_households_user_in_two_households(client, household_setup):
    """Пользователь в двух домохозяйствах видит оба с разными ролями, чужие не видит."""
    first_id = household_setup["household_id"]  # 1, домохозяйство «Дом»
    owner = household_setup["owner"]    # {"id": 1, "headers": {...}}
    member = household_setup["member"]  # {"id": 2, "headers": {...}}

    # member создаёт собственное домохозяйство. В нём он владелец,
    # а в «Доме» остаётся обычным участником.
    response = client.post(
        "/households",
        json={"name": "Дача"},
        headers=member["headers"],
    )
    assert response.status_code == 201, response.text
    second_id = response.json()["id"]  # 2

    response = client.get("/households", headers=member["headers"])
    assert response.status_code == 200, response.text

    # items → [
    #   {"id": 1, "name": "Дом",   "created_at": "...", "role": "member"},
    #   {"id": 2, "name": "Дача",  "created_at": "...", "role": "owner"},
    # ]
    items = response.json()

    # Словарь «id домохозяйства → роль»: {1: "member", 2: "owner"}
    roles = {item["id"]: item["role"] for item in items}
    assert roles == {first_id: "member", second_id: "owner"}

    # Список id в порядке появления в ответе: [1, 2].
    # Сначала должно идти старое домохозяйство.
    assert [item["id"] for item in items] == [first_id, second_id]

    # owner в «Даче» не состоит, поэтому видит только «Дом»
    response = client.get("/households", headers=owner["headers"])
    assert [item["id"] for item in response.json()] == [first_id]