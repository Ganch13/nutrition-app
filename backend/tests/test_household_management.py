"""Тесты приглашений и управления участниками домохозяйства (шаг 62)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import HouseholdInvite
from tests.helpers import AuthUser, register_and_login

# Допустимые символы кода (как INVITE_ALPHABET в household_services)
CODE_ALPHABET = set("ABCDEFGHJKMNPQRSTUVWXYZ23456789")


# ---------- Помощники ----------

def make_household(client, owner: AuthUser) -> int:
    """Владелец создаёт домохозяйство «Дом». Возвращает его id, например 1."""
    response = client.post("/households", json={"name": "Дом"}, headers=owner["headers"])
    assert response.status_code == 201, response.text
    return response.json()["id"]


def make_invite(client, owner: AuthUser, household_id: int) -> dict:
    """Создаёт код. Возвращает {"id": 1, "household_id": 1, "code": "K7M29QXP", ...}."""
    response = client.post(f"/households/{household_id}/invites", headers=owner["headers"])
    assert response.status_code == 201, response.text
    return response.json()


def join_with_code(client, user: AuthUser, code: str):
    """Пользователь вступает по коду. Возвращает ответ целиком, чтобы тест проверил статус."""
    return client.post("/households/join", json={"code": code}, headers=user["headers"])


def add_via_invite(client, owner: AuthUser, household_id: int, user: AuthUser) -> None:
    """Короткий путь: владелец создаёт код, пользователь по нему вступает."""
    invite = make_invite(client, owner, household_id)
    response = join_with_code(client, user, invite["code"])
    assert response.status_code == 200, response.text


def set_role(client, owner: AuthUser, household_id: int, user: AuthUser, role: str):
    """Владелец меняет роль участника. Возвращает ответ."""
    return client.patch(
        f"/households/{household_id}/members/{user['id']}",
        json={"role": role},
        headers=owner["headers"],
    )


def remove(client, actor: AuthUser, household_id: int, target: AuthUser):
    """actor удаляет target (или выходит сам, если это один человек). Возвращает ответ."""
    return client.delete(
        f"/households/{household_id}/members/{target['id']}",
        headers=actor["headers"],
    )


# ---------- Создание кода ----------

def test_owner_can_create_invite(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    household_id = make_household(client, owner)

    invite = make_invite(client, owner, household_id)
    # invite → {"id": 1, "household_id": 1, "code": "K7M29QXP", "expires_at": "...", ...}

    assert invite["household_id"] == household_id
    assert len(invite["code"]) == 8
    assert set(invite["code"]) <= CODE_ALPHABET
    expires_at = datetime.fromisoformat(invite["expires_at"])
    assert expires_at > datetime.now(timezone.utc) + timedelta(days=6)


def test_regular_member_cannot_create_invite(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    guest = register_and_login(client, "guest@example.com", "Guest")
    household_id = make_household(client, owner)
    add_via_invite(client, owner, household_id, guest)

    response = client.post(f"/households/{household_id}/invites", headers=guest["headers"])
    assert response.status_code == 403


def test_outsider_cannot_create_invite(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    outsider = register_and_login(client, "outsider@example.com", "Outsider")
    household_id = make_household(client, owner)

    response = client.post(f"/households/{household_id}/invites", headers=outsider["headers"])
    assert response.status_code == 403


def test_create_invite_requires_token(client):
    response = client.post("/households/1/invites")
    assert response.status_code == 401


def test_invite_for_unknown_household_returns_404(client):
    owner = register_and_login(client, "owner@example.com", "Owner")

    response = client.post("/households/999999/invites", headers=owner["headers"])
    assert response.status_code == 404


# ---------- Вступление по коду ----------

def test_user_joins_by_code(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    guest = register_and_login(client, "guest@example.com", "Guest")
    household_id = make_household(client, owner)
    invite = make_invite(client, owner, household_id)

    response = join_with_code(client, guest, invite["code"])
    assert response.status_code == 200, response.text
    # response.json() → {"id": 1, "name": "Дом", "created_at": "...", "role": "member"}
    assert response.json()["id"] == household_id
    assert response.json()["name"] == "Дом"
    assert response.json()["role"] == "member"

    # Домохозяйство появилось в списке гостя
    households = client.get("/households", headers=guest["headers"]).json()
    assert [item["id"] for item in households] == [household_id]

    # Гость виден в списке участников, и у каждого есть имя
    members = client.get(f"/households/{household_id}/members", headers=guest["headers"]).json()
    names = {member["user_id"]: member["name"] for member in members}
    assert names == {owner["id"]: "Owner", guest["id"]: "Guest"}


def test_code_is_single_use(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    first = register_and_login(client, "first@example.com", "First")
    second = register_and_login(client, "second@example.com", "Second")
    household_id = make_household(client, owner)
    invite = make_invite(client, owner, household_id)

    assert join_with_code(client, first, invite["code"]).status_code == 200
    assert join_with_code(client, second, invite["code"]).status_code == 404


def test_code_tolerates_case_spaces_and_dash(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    guest = register_and_login(client, "guest@example.com", "Guest")
    household_id = make_household(client, owner)
    code = make_invite(client, owner, household_id)["code"]  # "K7M29QXP"

    messy = f"  {code[:4].lower()}-{code[4:].lower()}  "  # "  k7m2-9qxp  "
    assert join_with_code(client, guest, messy).status_code == 200


def test_unknown_and_used_codes_give_the_same_error(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    guest = register_and_login(client, "guest@example.com", "Guest")
    other = register_and_login(client, "other@example.com", "Other")
    household_id = make_household(client, owner)
    invite = make_invite(client, owner, household_id)
    assert join_with_code(client, guest, invite["code"]).status_code == 200

    used = join_with_code(client, other, invite["code"])
    unknown = join_with_code(client, other, "ZZZZZZZZ")

    assert used.status_code == 404
    assert unknown.status_code == 404
    # По тексту ответа нельзя понять, существовал ли такой код
    assert used.json()["detail"] == unknown.json()["detail"]


def test_expired_code_is_rejected(client, engine):
    owner = register_and_login(client, "owner@example.com", "Owner")
    guest = register_and_login(client, "guest@example.com", "Guest")
    household_id = make_household(client, owner)
    invite = make_invite(client, owner, household_id)

    # «Старим» код напрямую в тестовой базе: ждать 7 дней мы не можем
    with Session(engine) as db:
        row = db.get(HouseholdInvite, invite["id"])
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

    assert join_with_code(client, guest, invite["code"]).status_code == 404


def test_member_joining_twice_gets_409_and_code_is_not_spent(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    guest = register_and_login(client, "guest@example.com", "Guest")
    third = register_and_login(client, "third@example.com", "Third")
    household_id = make_household(client, owner)
    add_via_invite(client, owner, household_id, guest)

    second_invite = make_invite(client, owner, household_id)
    # Гость уже в семье: 409, код не тратится
    assert join_with_code(client, guest, second_invite["code"]).status_code == 409
    # Поэтому им может воспользоваться другой человек
    assert join_with_code(client, third, second_invite["code"]).status_code == 200


# ---------- Список и отзыв кодов ----------

def test_invite_list_shows_only_active_codes_to_managers(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    guest = register_and_login(client, "guest@example.com", "Guest")
    household_id = make_household(client, owner)
    used = make_invite(client, owner, household_id)
    unused = make_invite(client, owner, household_id)
    assert join_with_code(client, guest, used["code"]).status_code == 200

    response = client.get(f"/households/{household_id}/invites", headers=owner["headers"])
    assert response.status_code == 200
    # Использованный код из списка исчез
    assert [item["code"] for item in response.json()] == [unused["code"]]

    # Обычный участник кодов не видит
    response = client.get(f"/households/{household_id}/invites", headers=guest["headers"])
    assert response.status_code == 403


def test_revoke_invite(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    guest = register_and_login(client, "guest@example.com", "Guest")
    household_id = make_household(client, owner)
    invite = make_invite(client, owner, household_id)
    url = f"/households/{household_id}/invites/{invite['id']}"

    # Обычный участник отзывать не может (сначала его надо добавить другим кодом)
    add_via_invite(client, owner, household_id, guest)
    assert client.delete(url, headers=guest["headers"]).status_code == 403

    assert client.delete(url, headers=owner["headers"]).status_code == 204
    # Повторное удаление: приглашения уже нет
    assert client.delete(url, headers=owner["headers"]).status_code == 404

    # Отозванный код не работает
    newcomer = register_and_login(client, "new@example.com", "New")
    assert join_with_code(client, newcomer, invite["code"]).status_code == 404


def test_cannot_revoke_invite_of_another_household(client):
    owner_one = register_and_login(client, "one@example.com", "One")
    owner_two = register_and_login(client, "two@example.com", "Two")
    household_one = make_household(client, owner_one)
    household_two = make_household(client, owner_two)
    invite_of_one = make_invite(client, owner_one, household_one)

    # owner_two управляет своим домохозяйством, но подставляет чужой id приглашения
    response = client.delete(
        f"/households/{household_two}/invites/{invite_of_one['id']}",
        headers=owner_two["headers"],
    )
    assert response.status_code == 404


# ---------- Роли ----------

def test_owner_can_promote_and_demote_member(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    guest = register_and_login(client, "guest@example.com", "Guest")
    household_id = make_household(client, owner)
    add_via_invite(client, owner, household_id, guest)

    response = set_role(client, owner, household_id, guest, "admin")
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "admin"
    assert response.json()["name"] == "Guest"

    # Администратор теперь может создавать приглашения
    invites_url = f"/households/{household_id}/invites"
    assert client.post(invites_url, headers=guest["headers"]).status_code == 201

    # После понижения такое право исчезает
    assert set_role(client, owner, household_id, guest, "member").status_code == 200
    assert client.post(invites_url, headers=guest["headers"]).status_code == 403


def test_only_owner_can_change_roles(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    admin = register_and_login(client, "admin@example.com", "Admin")
    member = register_and_login(client, "member@example.com", "Member")
    outsider = register_and_login(client, "outsider@example.com", "Outsider")
    household_id = make_household(client, owner)
    add_via_invite(client, owner, household_id, admin)
    add_via_invite(client, owner, household_id, member)
    assert set_role(client, owner, household_id, admin, "admin").status_code == 200

    # Ни администратор, ни участник, ни посторонний роли менять не могут
    assert set_role(client, admin, household_id, member, "admin").status_code == 403
    assert set_role(client, member, household_id, member, "admin").status_code == 403
    assert set_role(client, outsider, household_id, member, "admin").status_code == 403


def test_owner_role_cannot_be_changed(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    household_id = make_household(client, owner)

    assert set_role(client, owner, household_id, owner, "member").status_code == 409


def test_role_change_validation(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    guest = register_and_login(client, "guest@example.com", "Guest")
    household_id = make_household(client, owner)
    add_via_invite(client, owner, household_id, guest)

    # Роль «owner» назначить нельзя: схема принимает только admin и member
    assert set_role(client, owner, household_id, guest, "owner").status_code == 422

    # Несуществующий участник
    response = client.patch(
        f"/households/{household_id}/members/999999",
        json={"role": "admin"},
        headers=owner["headers"],
    )
    assert response.status_code == 404


# ---------- Удаление и выход ----------

def test_owner_removes_member(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    guest = register_and_login(client, "guest@example.com", "Guest")
    household_id = make_household(client, owner)
    add_via_invite(client, owner, household_id, guest)

    assert remove(client, owner, household_id, guest).status_code == 204

    # Удалённый больше не видит домохозяйство
    members_url = f"/households/{household_id}/members"
    assert client.get(members_url, headers=guest["headers"]).status_code == 403
    assert client.get("/households", headers=guest["headers"]).json() == []
    # А у владельца остался один участник
    assert len(client.get(members_url, headers=owner["headers"]).json()) == 1


def test_admin_removes_only_regular_members(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    admin = register_and_login(client, "admin@example.com", "Admin")
    other_admin = register_and_login(client, "admin2@example.com", "Admin Two")
    member = register_and_login(client, "member@example.com", "Member")
    household_id = make_household(client, owner)
    for user in (admin, other_admin, member):
        add_via_invite(client, owner, household_id, user)
    assert set_role(client, owner, household_id, admin, "admin").status_code == 200
    assert set_role(client, owner, household_id, other_admin, "admin").status_code == 200

    # Обычного участника администратор удалить может
    assert remove(client, admin, household_id, member).status_code == 204
    # Другого администратора и владельца нет
    assert remove(client, admin, household_id, other_admin).status_code == 403
    assert remove(client, admin, household_id, owner).status_code == 403
    # Владелец может удалить администратора
    assert remove(client, owner, household_id, other_admin).status_code == 204


def test_regular_member_cannot_remove_others(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    first = register_and_login(client, "first@example.com", "First")
    second = register_and_login(client, "second@example.com", "Second")
    household_id = make_household(client, owner)
    add_via_invite(client, owner, household_id, first)
    add_via_invite(client, owner, household_id, second)

    assert remove(client, first, household_id, second).status_code == 403
    assert remove(client, first, household_id, owner).status_code == 403


def test_member_can_leave(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    guest = register_and_login(client, "guest@example.com", "Guest")
    household_id = make_household(client, owner)
    add_via_invite(client, owner, household_id, guest)

    assert remove(client, guest, household_id, guest).status_code == 204
    assert client.get("/households", headers=guest["headers"]).json() == []


def test_owner_cannot_leave(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    household_id = make_household(client, owner)

    assert remove(client, owner, household_id, owner).status_code == 409
    # Домохозяйство на месте
    assert len(client.get("/households", headers=owner["headers"]).json()) == 1


def test_remove_unknown_member_returns_404(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    household_id = make_household(client, owner)

    response = client.delete(f"/households/{household_id}/members/999999", headers=owner["headers"])
    assert response.status_code == 404


def test_outsider_cannot_remove_members(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    guest = register_and_login(client, "guest@example.com", "Guest")
    outsider = register_and_login(client, "outsider@example.com", "Outsider")
    household_id = make_household(client, owner)
    add_via_invite(client, owner, household_id, guest)

    assert remove(client, outsider, household_id, guest).status_code == 403


# ---------- Связь с финансами ----------

def test_removed_member_loses_family_ledger_access(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    guest = register_and_login(client, "guest@example.com", "Guest")
    household_id = make_household(client, owner)
    add_via_invite(client, owner, household_id, guest)

    response = client.post(
        "/finance/ledgers",
        json={"kind": "household", "household_id": household_id, "currency": "EUR"},
        headers=owner["headers"],
    )
    assert response.status_code in (200, 201), response.text

    # Гость видит семейную книгу
    ledgers = client.get("/finance/ledgers", headers=guest["headers"]).json()
    assert household_id in [item["household_id"] for item in ledgers]

    # После удаления из семьи книга пропадает из его списка
    assert remove(client, owner, household_id, guest).status_code == 204
    ledgers = client.get("/finance/ledgers", headers=guest["headers"]).json()
    assert household_id not in [item["household_id"] for item in ledgers]