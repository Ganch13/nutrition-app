from tests.helpers import register_and_login


def make_meal(client, user, eaten_at: str, description: str) -> dict:
    """Создаёт запись о приёме пищи и возвращает ответ сервера.

    Аргументы: user — результат register_and_login; eaten_at — момент в формате
    ISO с часовым поясом, например "2026-10-23T10:00:00Z"; description — "Завтрак".
    Результат: {"id": 1, "description": "Завтрак", "calories": "100.00", ...}
    """
    response = client.post(
        f"/users/{user['id']}/meal-entries",
        json={
            "eaten_at": eaten_at,
            "meal_type": "snack",
            "description": description,
            "calories": 100,
            "protein_g": 5,
            "fat_g": 3,
            "carbs_g": 10,
        },
        headers=user["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_session(client, user) -> dict:
    """Создаёт тренировочную сессию (статус planned) и возвращает ответ сервера."""
    response = client.post(
        f"/users/{user['id']}/training-sessions",
        json={
            "name": "Баскетбол",
            "start_at": "2026-10-23T17:00:00Z",
            "end_at": "2026-10-23T19:00:00Z",
        },
        headers=user["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_daily_entries_use_user_timezone(client):
    """День считается по часовому поясу пользователя, а не по UTC."""
    # 23 октября 2026 в Берлине действует UTC+2
    user = register_and_login(client, "berlin@example.com", "Berlin", timezone="Europe/Berlin")
    make_meal(client, user, "2026-10-22T22:30:00Z", "A")  # 00:30 23 октября по Берлину
    make_meal(client, user, "2026-10-23T10:00:00Z", "B")  # 12:00 23 октября
    make_meal(client, user, "2026-10-23T22:30:00Z", "C")  # 00:30 24 октября, не наш день

    url = f"/users/{user['id']}/nutrition"
    params = {"target_date": "2026-10-23"}

    response = client.get(f"{url}/daily-entries", params=params, headers=user["headers"])
    assert response.status_code == 200, response.text
    # Ожидаем записи A и B по времени
    assert [item["description"] for item in response.json()] == ["A", "B"]

    # Дневная сводка считает тот же день и видит те же две записи
    summary = client.get(f"{url}/daily-summary", params=params, headers=user["headers"])
    assert summary.json()["entries_count"] == 2


def test_daily_entries_forbidden_for_other_user(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    other = register_and_login(client, "other@example.com", "Other")

    response = client.get(
        f"/users/{owner['id']}/nutrition/daily-entries",
        params={"target_date": "2026-10-23"},
        headers=other["headers"],
    )
    assert response.status_code == 403


def test_delete_meal_entry(client):
    user = register_and_login(client, "meal@example.com", "Meal")
    entry = make_meal(client, user, "2026-10-23T10:00:00Z", "To delete")
    url = f"/users/{user['id']}/meal-entries/{entry['id']}"

    # Первое удаление успешно и ничего не возвращает
    assert client.delete(url, headers=user["headers"]).status_code == 204

    response = client.get(
        f"/users/{user['id']}/nutrition/daily-entries",
        params={"target_date": "2026-10-23"},
        headers=user["headers"],
    )
    assert response.json() == []

    # Повторное удаление: записи уже нет
    assert client.delete(url, headers=user["headers"]).status_code == 404


def test_cannot_delete_other_users_meal_entry(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    other = register_and_login(client, "other@example.com", "Other")
    entry = make_meal(client, owner, "2026-10-23T10:00:00Z", "Owner meal")

    # other обращается к СВОЕМУ адресу, но к чужой записи
    response = client.delete(
        f"/users/{other['id']}/meal-entries/{entry['id']}",
        headers=other["headers"],
    )
    assert response.status_code == 404

    # Запись владельца осталась на месте
    response = client.get(
        f"/users/{owner['id']}/nutrition/daily-entries",
        params={"target_date": "2026-10-23"},
        headers=owner["headers"],
    )
    assert len(response.json()) == 1


def test_delete_weight_record(client):
    user = register_and_login(client, "weight@example.com", "Weight")

    response = client.post(
        f"/users/{user['id']}/weight-records",
        json={"measurement_date": "2026-10-23", "weight_kg": 80.5},
        headers=user["headers"],
    )
    assert response.status_code == 201, response.text
    url = f"/users/{user['id']}/weight-records/{response.json()['id']}"

    assert client.delete(url, headers=user["headers"]).status_code == 204

    listing = client.get(f"/users/{user['id']}/weight-records", headers=user["headers"])
    assert listing.json() == []

    assert client.delete(url, headers=user["headers"]).status_code == 404


def test_update_training_session_status(client):
    user = register_and_login(client, "train@example.com", "Train")
    session = make_session(client, user)
    url = f"/users/{user['id']}/training-sessions/{session['id']}"

    response = client.patch(url, json={"status": "completed"}, headers=user["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"

    # Пустое тело и неизвестный статус отклоняются
    assert client.patch(url, json={}, headers=user["headers"]).status_code == 422
    response = client.patch(url, json={"status": "nonsense"}, headers=user["headers"])
    assert response.status_code == 422


def test_cannot_update_other_users_training_session(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    other = register_and_login(client, "other@example.com", "Other")
    session = make_session(client, owner)

    response = client.patch(
        f"/users/{other['id']}/training-sessions/{session['id']}",
        json={"status": "skipped"},
        headers=other["headers"],
    )
    assert response.status_code == 404