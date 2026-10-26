from tests.helpers import register_and_login


def make_session_with_workout(client, user) -> tuple[dict, dict]:
    """Создаёт сессию и один блок в ней; возвращает (сессия, блок).

    Результат, например: ({"id": 1, "name": "Зал", ...}, {"id": 1, "name": "Жим", ...})
    """
    response = client.post(
        f"/users/{user['id']}/training-sessions",
        json={
            "name": "Зал",
            "start_at": "2026-10-23T17:00:00Z",
            "end_at": "2026-10-23T19:00:00Z",
        },
        headers=user["headers"],
    )
    assert response.status_code == 201, response.text
    session = response.json()

    response = client.post(
        f"/users/{user['id']}/training-sessions/{session['id']}/workouts",
        json={
            "name": "Жим",
            "load_type": "strength",
            "planned_intensity": "moderate",
            "start_at": "2026-10-23T17:00:00Z",
            "end_at": "2026-10-23T18:00:00Z",
        },
        headers=user["headers"],
    )
    assert response.status_code == 201, response.text
    return session, response.json()


def test_delete_goal(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    other = register_and_login(client, "other@example.com", "Other")

    response = client.post(
        f"/users/{owner['id']}/goals",
        json={"goal_type": "fat_loss", "start_date": "2026-10-26"},
        headers=owner["headers"],
    )
    assert response.status_code == 201, response.text
    goal_id = response.json()["id"]

    # Чужой пользователь удалить цель не может: для него её «нет»
    foreign = client.delete(f"/users/{other['id']}/goals/{goal_id}", headers=other["headers"])
    assert foreign.status_code == 404

    url = f"/users/{owner['id']}/goals/{goal_id}"
    assert client.delete(url, headers=owner["headers"]).status_code == 204

    listing = client.get(f"/users/{owner['id']}/goals", headers=owner["headers"])
    assert listing.json() == []

    assert client.delete(url, headers=owner["headers"]).status_code == 404


def test_delete_training_session_removes_its_workouts(client):
    owner = register_and_login(client, "owner@example.com", "Owner")
    other = register_and_login(client, "other@example.com", "Other")
    session, _ = make_session_with_workout(client, owner)

    # Чужой пользователь: 404, сессия остаётся
    foreign = client.delete(
        f"/users/{other['id']}/training-sessions/{session['id']}",
        headers=other["headers"],
    )
    assert foreign.status_code == 404

    url = f"/users/{owner['id']}/training-sessions/{session['id']}"
    assert client.delete(url, headers=owner["headers"]).status_code == 204

    # Сессии больше нет, а значит нет и доступа к её блокам
    listing = client.get(f"/users/{owner['id']}/training-sessions", headers=owner["headers"])
    assert listing.json() == []
    workouts = client.get(f"{url}/workouts", headers=owner["headers"])
    assert workouts.status_code == 404


def test_delete_workout(client):
    user = register_and_login(client, "workout@example.com", "Workout")
    session, workout = make_session_with_workout(client, user)
    url = f"/users/{user['id']}/training-sessions/{session['id']}/workouts/{workout['id']}"

    assert client.delete(url, headers=user["headers"]).status_code == 204

    listing = client.get(
        f"/users/{user['id']}/training-sessions/{session['id']}/workouts",
        headers=user["headers"],
    )
    assert listing.json() == []

    assert client.delete(url, headers=user["headers"]).status_code == 404