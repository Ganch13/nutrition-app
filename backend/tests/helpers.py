from typing import TypedDict


class AuthUser(TypedDict):
    """Описание словаря, который возвращает register_and_login.

    TypedDict — «словарь с известными ключами и типами значений». Во время
    выполнения это обычный словарь, а типы нужны PyCharm и другим инструментам
    проверки кода: они знают, что под "id" лежит число, а под "headers" словарь.

    Пример данных:
        {"id": 1, "headers": {"Authorization": "Bearer eyJhbGciOi..."}}
    """

    # Идентификатор пользователя в базе, например 1
    id: int

    # Заголовки запроса от имени этого пользователя;
    # ключи и значения — строки
    headers: dict[str, str]


def register_and_login(client, email: str, name: str = "Test User") -> AuthUser:
    """Регистрирует пользователя, входит и возвращает его id и заголовки с токеном.

    Аргументы:
        client — виртуальный клиент из фикстуры client
        email  — например "owner@example.com"
        name   — например "Owner"

    Результат:
        {"id": 1, "headers": {"Authorization": "Bearer eyJhbGciOi..."}}
    """
    # Пароль одинаковый для всех тестовых пользователей; длина больше 12 символов,
    # как требует схема регистрации
    password = "very-strong-password-123"

    # Регистрация: POST-запрос с телом JSON, как из Swagger
    response = client.post(
        "/auth/register",
        json={
            "name": name,
            "email": email,
            "password": password,
            "height_cm": 180,
        },
    )
    # response.status_code → 201
    # response.json() → {"id": 1, "name": "Owner", "age": None, "birth_date": None,
    #                    "sex": None, "height_cm": 180, "occupation": None,
    #                    "timezone": "UTC", "created_at": "2026-10-23T..."}
    assert response.status_code == 201, response.text
    user_id = response.json()["id"]  # 1

    # Вход: получаем токен
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    # response.json() → {"access_token": "eyJhbGciOi...", "token_type": "bearer"}
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]  # "eyJhbGciOi..."

    # Возвращаем словарь с тем же набором ключей, что описан в AuthUser
    return {"id": user_id, "headers": {"Authorization": f"Bearer {token}"}}