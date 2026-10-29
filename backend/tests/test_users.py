from tests.helpers import register_and_login


def test_get_me_requires_token(client):
    """Без токена профиль недоступен: ожидаем 401."""
    # client — виртуальный клиент из фикстуры client; заголовков не передаём
    response = client.get("/users/me")

    # 401 Unauthorized: запрос не аутентифицирован
    assert response.status_code == 401


def test_get_me_returns_current_user(client):
    """Эндпоинт возвращает профиль владельца токена и не раскрывает пароль."""
    # user → {"id": 1, "headers": {"Authorization": "Bearer eyJhbGciOi..."}}
    user = register_and_login(client, "me@example.com", "Me User")

    response = client.get("/users/me", headers=user["headers"])

    # Статус 200 заодно подтверждает порядок маршрутов: если бы /users/{user_id}
    # стоял выше, слово "me" дало бы 422
    assert response.status_code == 200, response.text

    # body → {"id": 1, "name": "Me User", "age": None, "birth_date": None,
    #         "sex": None, "height_cm": 180, "occupation": None,
    #         "timezone": "UTC", "created_at": "2026-10-22T..."}
    body = response.json()
    assert body["id"] == user["id"]
    assert body["name"] == "Me User"

    # Хеш пароля не должен попадать в ответ ни при каких условиях
    assert "password_hash" not in body


def test_get_me_returns_data_of_token_owner(client):
    """Каждый пользователь видит свои данные, а не чужие."""
    alice = register_and_login(client, "alice@example.com", "Alice")  # id 1
    bob = register_and_login(client, "bob@example.com", "Bob")        # id 2

    # Запросы идут с токенами разных людей
    alice_response = client.get("/users/me", headers=alice["headers"])
    bob_response = client.get("/users/me", headers=bob["headers"])

    # alice_response.json()["name"] → "Alice", bob_response.json()["name"] → "Bob"
    assert alice_response.json()["name"] == "Alice"
    assert bob_response.json()["name"] == "Bob"

def test_profile_shows_own_email(client):
    """ТЗ 29.10.26(2), п. 6: профиль (GET /users/me и GET /users/{id}) отдаёт email владельца для показа в настройках."""
    user = register_and_login(client, "Mail.Owner@Example.com")

    me = client.get("/users/me", headers=user["headers"])
    assert me.status_code == 200
    # Почта хранится в нижнем регистре (как при входе)
    assert me.json()["email"] == "mail.owner@example.com"

    by_id = client.get(f"/users/{user['id']}", headers=user["headers"])
    assert by_id.json()["email"] == "mail.owner@example.com"
