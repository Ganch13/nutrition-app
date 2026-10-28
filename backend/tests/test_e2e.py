"""Шаг 71. Сквозные проверки: целые сценарии «как живёт семья» и проверка защиты всех адресов API.

В отличие от остальных тестов, здесь нет проверки одной функции: каждый сценарий проходит путь
пользователя через несколько разделов (регистрация → профиль → расписание → нормы → меню → закупки →
семья → фото → финансы) так, как это делает интерфейс.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from security import create_access_token
from tests.helpers import new_household, register_and_login
from tests.photo_samples import JPEG_WITH_EXIF
from tests.test_finance import add_transaction, category_id, create_household_ledger
from tests.test_meal_plan import MONDAY, at, local_minutes, week
from tests.test_norms import add_goal, add_weight, setup_profile

# Адреса, которые открыты без входа. Любой новый адрес без защиты должен попасть сюда сознательно.
PUBLIC_OPERATIONS = {
    ("GET", "/health"),
    ("POST", "/auth/register"),
    ("POST", "/auth/login"),
    ("POST", "/auth/refresh"),
    ("POST", "/auth/logout"),
}

HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def all_operations(client) -> list[tuple[str, str]]:
    """Все пары (метод, адрес) из описания API (OpenAPI): [("GET", "/users/{user_id}"), ...]."""
    schema = client.get("/openapi.json").json()
    return [
        (method.upper(), path)
        for path, item in schema["paths"].items()
        for method in item
        if method in HTTP_METHODS
    ]


def fill(path: str, **ids: int) -> str:
    """Подставляет числа в адрес: ("/users/{user_id}/goals/{goal_id}", user_id=3) → "/users/3/goals/1"."""
    for name in set(part.split("}")[0] for part in path.split("{")[1:]):
        path = path.replace("{" + name + "}", str(ids.get(name, 1)))
    return path


def call(client, method: str, url: str, headers=None):
    """Запрос с пустым JSON-телом: защита должна сработать раньше проверки тела."""
    return client.request(method, url, headers=headers or {}, json={})


# ---------------------------------------------------------------- защита всех адресов


def test_only_known_addresses_are_public(client):
    schema = client.get("/openapi.json").json()
    open_operations = {
        (method.upper(), path)
        for path, item in schema["paths"].items()
        for method, operation in item.items()
        if method in HTTP_METHODS and not operation.get("security")
    }
    assert open_operations == PUBLIC_OPERATIONS


def test_every_protected_address_rejects_missing_or_bad_tokens(client):
    user = register_and_login(client, "a@example.com")
    expired = create_access_token({"sub": str(user["id"])}, expires_delta=timedelta(minutes=-1))
    bad_tokens = [None, "garbage", expired]

    checked = 0
    for method, path in all_operations(client):
        if (method, path) in PUBLIC_OPERATIONS:
            continue
        url = fill(path, user_id=user["id"])
        for token in bad_tokens:
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            response = call(client, method, url, headers)
            assert response.status_code == 401, (method, path, token, response.status_code)
        checked += 1
    assert checked > 80  # проверка действительно прошла по всему API, а не по паре адресов


def test_user_addresses_reject_other_users(client):
    owner = register_and_login(client, "a@example.com")
    stranger = register_and_login(client, "b@example.com")

    checked = 0
    for method, path in all_operations(client):
        if not path.startswith("/users/{user_id}"):
            continue
        response = call(client, method, fill(path, user_id=owner["id"]), stranger["headers"])
        assert response.status_code == 403, (method, path, response.status_code, response.text)
        checked += 1
    assert checked > 50


def test_household_addresses_reject_non_members(client):
    owner = register_and_login(client, "a@example.com")
    stranger = register_and_login(client, "b@example.com")
    household_id = new_household(client, owner)

    schema = client.get("/openapi.json").json()
    checked = 0
    for method, path in all_operations(client):
        if "{household_id}" not in path:
            continue
        response = call(client, method, fill(path, household_id=household_id), stranger["headers"])
        # Если у адреса есть тело запроса, FastAPI сначала проверяет его форму (422 без обращения к
        # данным семьи); права на конкретные действия с корректным телом проверяют тесты семьи.
        has_body = "requestBody" in schema["paths"][path][method.lower()]
        allowed = {403, 422} if has_body else {403}
        assert response.status_code in allowed, (method, path, response.status_code, response.text)
        checked += 1
    assert checked >= 12


def test_unknown_user_in_token_is_rejected(client):
    """Токен настоящий, но пользователя уже нет — доступа нет."""
    ghost = create_access_token({"sub": "99999"})
    response = client.get("/users/me", headers={"Authorization": f"Bearer {ghost}"})
    assert response.status_code == 401


def test_token_cannot_be_used_after_signature_change(client):
    user = register_and_login(client, "a@example.com")
    token = user["headers"]["Authorization"].split()[1]
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    response = client.get("/users/me", headers={"Authorization": f"Bearer {tampered}"})
    assert response.status_code == 401


# ---------------------------------------------------------------- сценарий недели

TUESDAY = "2026-10-27"


def create_user(client, email, name):
    user = register_and_login(client, email, name=name, timezone="Europe/Moscow")
    return user


def test_family_week_from_registration_to_leaving(client, upload_dir):
    # 1. Регистрация и профили: Даня (80 кг) и Леся (60 кг), оба в Москве
    danya = create_user(client, "danya@example.com", "Даня")
    lesya = create_user(client, "lesya@example.com", "Леся")
    for user, sex, kg in ((danya, "male", 80), (lesya, "female", 60)):
        setup_profile(client, user, sex=sex)
        add_weight(client, user, "2026-10-20", kg)
    add_goal(client, danya, goal_type="fat_loss")
    profile = client.get("/users/me", headers=lesya["headers"]).json()
    assert profile["name"] == "Леся" and profile["age"] is not None

    # 2. Расписание: Даня на работе по будням, Леся ложится в 02:00; во вторник у Дани баскетбол в 19:00
    response = client.post(
        f"/users/{danya['id']}/schedule-events/series",
        json={"event_type": "work", "title": "Работа", "weekdays": [0, 1, 2, 3, 4], "start_time": "09:00",
              "end_time": "18:00", "from_date": MONDAY, "weeks": 1},
        headers=danya["headers"],
    )
    assert response.status_code == 201, response.text
    response = client.post(
        f"/users/{lesya['id']}/schedule-events/series",
        json={"event_type": "sleep", "title": "Сон", "weekdays": [0, 1, 2, 3, 4, 5, 6], "start_time": "02:00",
              "end_time": "10:00", "from_date": MONDAY, "weeks": 1},
        headers=lesya["headers"],
    )
    assert response.status_code == 201, response.text
    session = client.post(
        f"/users/{danya['id']}/training-sessions",
        json={"name": "Баскетбол", "start_at": f"{TUESDAY}T19:00:00+03:00", "end_at": f"{TUESDAY}T21:00:00+03:00"},
        headers=danya["headers"],
    ).json()
    block = client.post(
        f"/users/{danya['id']}/training-sessions/{session['id']}/workouts",
        json={"name": "Игра", "load_type": "cardio", "planned_intensity": "high",
              "start_at": f"{TUESDAY}T19:00:00+03:00", "end_at": f"{TUESDAY}T21:00:00+03:00"},
        headers=danya["headers"],
    )
    assert block.status_code == 201, block.text

    # 3. Нормы: в день тренировки калорий больше, чем в понедельник; у Дани (тяжелее, с тренировкой) больше, чем у Леси
    def target(user, day):
        response = client.get(
            f"/users/{user['id']}/nutrition/targets", params={"target_date": day}, headers=user["headers"]
        )
        assert response.status_code == 200, response.text
        return response.json()

    assert target(danya, TUESDAY)["calories"] > target(danya, MONDAY)["calories"]
    assert target(danya, TUESDAY)["calories"] > target(lesya, TUESDAY)["calories"]

    # 4. Семья: приглашение, вступление, согласие на общий план
    household_id = new_household(client, danya, lesya, name="Наша семья")
    for user in (danya, lesya):
        response = client.put(
            f"/households/{household_id}/planning/me", json={"plans_together": True}, headers=user["headers"]
        )
        assert response.status_code == 200, response.text

    # 5. Меню: одна команда составляет неделю обоим, ужин общий
    response = client.post(
        f"/households/{household_id}/meal-plan/generate",
        json={"start": MONDAY, "days": 7},
        headers=lesya["headers"],  # составить может любой из участников
    )
    assert response.status_code == 200, response.text
    assert response.json()["shared_meals"] == 7 and response.json()["warnings"] == []

    for user in (danya, lesya):
        for day in week(client, user)["days"]:
            assert abs(float(day["planned_calories"]) / day["target"]["calories"] - 1) <= 0.08, (user["id"], day["date"])
    # Во вторник у Дани не стоит еды в окне перед баскетболом и во время него (18:00–21:00)
    for meal in week(client, danya)["days"][1]["meals"]:
        assert not (18 * 60 < local_minutes(meal["planned_at"]) < 21 * 60), meal["title"]
    # Общий ужин у обоих в одно время
    family = client.get(f"/households/{household_id}/meal-plan", params={"start": MONDAY}, headers=danya["headers"]).json()
    for day in family["days"]:
        dinners = [m["planned_at"] for member in day["members"] for m in member["meals"] if m["meal_type"] == "dinner"]
        assert len(dinners) == 2

    # 6. Даня съел завтрак в понедельник: запись попала в дневник, сводка дня обновилась
    breakfast = week(client, danya)["days"][0]["meals"][0]
    eaten = client.post(
        f"/users/{danya['id']}/meal-plan/meals/{breakfast['id']}/eat",
        json={"eaten_at": f"{MONDAY}T08:30:00+03:00"},
        headers=danya["headers"],
    )
    assert eaten.status_code == 200, eaten.text
    summary = client.get(
        f"/users/{danya['id']}/nutrition/daily-summary", params={"target_date": MONDAY}, headers=danya["headers"]
    ).json()
    assert summary["entries_count"] == 1
    assert float(summary["calories"]) == pytest.approx(float(breakfast["calories"]), abs=0.5)

    # 7. Закупки: общий список объединяет оба плана (съеденный завтрак Дани в него уже не входит)
    shopping = client.get(
        f"/households/{household_id}/shopping-list", params={"start": MONDAY, "days": 7}, headers=lesya["headers"]
    ).json()
    assert shopping["members"] == ["Даня", "Леся"] and shopping["meals_count"] == 55
    key = shopping["items"][0]["key"]
    client.put(
        f"/households/{household_id}/shopping-list/checks",
        json={"start": MONDAY, "key": key, "checked": True},
        headers=lesya["headers"],
    )
    after = client.get(
        f"/households/{household_id}/shopping-list", params={"start": MONDAY, "days": 7}, headers=danya["headers"]
    ).json()
    assert after["items"][0]["checked_by"] == "Леся" and after["checked_count"] == 1
    cooking = client.get(
        f"/households/{household_id}/cooking-plan", params={"start": MONDAY}, headers=danya["headers"]
    ).json()
    assert cooking["sessions"] and cooking["total_minutes"] > 0

    # 8. Фото прогресса: у каждого свои, чужие недоступны, на диске нет метаданных
    today = date.today().isoformat()
    uploaded = {}
    for user in (danya, lesya):
        response = client.post(
            f"/users/{user['id']}/progress-photos",
            params={"taken_on": today},
            content=JPEG_WITH_EXIF,
            headers={**user["headers"], "Content-Type": "image/jpeg"},
        )
        assert response.status_code == 201, response.text
        uploaded[user["id"]] = response.json()
    assert len(list(upload_dir.rglob("*.jpg"))) == 2
    assert all(b"SecretPhone" not in path.read_bytes() for path in upload_dir.rglob("*.jpg"))
    assert client.get(uploaded[danya["id"]]["url"], headers=lesya["headers"]).status_code == 403
    assert client.get(
        f"/users/{lesya['id']}/progress-photos/{uploaded[danya['id']]['id']}", headers=lesya["headers"]
    ).status_code == 404

    # 9. Финансы: общая книга семьи, Леся видит операцию Дани
    ledger = create_household_ledger(client, danya, household_id).json()
    food = category_id(client, danya, ledger["id"], "Продукты")
    add_transaction(client, danya, ledger["id"], food, 35, "2026-10-26", "Закупка на неделю")
    seen = client.get(
        f"/finance/ledgers/{ledger['id']}/transactions", params={"month": "2026-10"}, headers=lesya["headers"]
    )
    assert seen.status_code == 200 and [t["description"] for t in seen.json()] == ["Закупка на неделю"]

    # 10. Леся выходит из семьи: семейные адреса закрыты, у Дани её больше нет, а её личные данные на месте
    left = client.delete(f"/households/{household_id}/members/{lesya['id']}", headers=lesya["headers"])
    assert left.status_code == 204, left.text
    assert client.get(f"/households/{household_id}/meal-plan", params={"start": MONDAY}, headers=lesya["headers"]).status_code == 403
    assert client.get(f"/finance/ledgers/{ledger['id']}/transactions", params={"month": "2026-10"}, headers=lesya["headers"]).status_code in (403, 404)
    after_leave = client.get(
        f"/households/{household_id}/shopping-list", params={"start": MONDAY, "days": 7}, headers=danya["headers"]
    ).json()
    assert after_leave["members"] == ["Даня"]
    assert len(week(client, lesya)["days"][0]["meals"]) == 4
    assert client.get(uploaded[lesya["id"]]["url"], headers=lesya["headers"]).status_code == 200


def test_new_user_without_data_gets_helpful_answers_not_errors(client):
    """Первый вход: пока ничего не заполнено, разделы отвечают понятно, а не падают."""
    user = register_and_login(client, "new@example.com", "Новый")
    base = f"/users/{user['id']}"

    assert client.get(f"{base}/goals", headers=user["headers"]).json() == []
    assert client.get(f"{base}/weight-records", headers=user["headers"]).json() == []
    assert client.get(f"{base}/progress-photos", headers=user["headers"]).json() == []
    assert client.get("/households", headers=user["headers"]).json() == []
    assert client.get("/finance/ledgers", headers=user["headers"]).json() == []

    plan = week(client, user)
    assert plan["target_ready"] is False and plan["warnings"] and all(d["meals"] == [] for d in plan["days"])
    generate = client.post(f"{base}/meal-plan/generate", json={"start": MONDAY}, headers=user["headers"])
    assert generate.status_code == 409 and "вес" in generate.json()["detail"]
    shopping = client.get(f"{base}/shopping-list", params={"start": MONDAY}, headers=user["headers"]).json()
    assert shopping["items"] == [] and shopping["meals_count"] == 0
    cooking = client.get(f"{base}/cooking-plan", params={"start": MONDAY}, headers=user["headers"]).json()
    assert cooking["sessions"] == []
    foods = client.get("/foods", params={"q": "греч"}, headers=user["headers"]).json()
    assert foods["items"], "справочник продуктов должен быть доступен сразу после регистрации"
    recipes = client.get("/recipes", headers=user["headers"]).json()
    assert recipes["items"], "встроенные рецепты должны быть доступны сразу после регистрации"


def test_two_families_do_not_see_each_other(client):
    """Две независимые семьи на одном сервере: данные не пересекаются."""
    users = {}
    for family_name, names in (("A", ("a1", "a2")), ("B", ("b1", "b2"))):
        members = []
        for name in names:
            user = register_and_login(client, f"{name}@example.com", name, timezone="Europe/Moscow")
            setup_profile(client, user)
            add_weight(client, user, "2026-10-20", 70)
            members.append(user)
        household_id = new_household(client, members[0], members[1], name=f"Семья {family_name}")
        for user in members:
            client.put(f"/households/{household_id}/planning/me", json={"plans_together": True}, headers=user["headers"])
        response = client.post(
            f"/households/{household_id}/meal-plan/generate", json={"start": MONDAY, "days": 2}, headers=members[0]["headers"]
        )
        assert response.status_code == 200, response.text
        users[family_name] = (household_id, members)

    (a_id, (a1, a2)), (b_id, (b1, b2)) = users["A"], users["B"]
    for household_id, viewer in ((a_id, a1), (b_id, b1)):
        view = client.get(f"/households/{household_id}/meal-plan", params={"start": MONDAY}, headers=viewer["headers"]).json()
        assert len(view["members"]) == 2
    names_a = {m["name"] for m in client.get(f"/households/{a_id}/planning", headers=a1["headers"]).json()["members"]}
    assert names_a == {"a1", "a2"}
    # Чужая семья закрыта целиком
    assert client.get(f"/households/{b_id}/meal-plan", params={"start": MONDAY}, headers=a1["headers"]).status_code == 403
    assert client.get(f"/households/{b_id}/shopping-list", params={"start": MONDAY}, headers=a2["headers"]).status_code == 403
    assert client.get(f"/households/{b_id}/members", headers=a1["headers"]).status_code == 403
