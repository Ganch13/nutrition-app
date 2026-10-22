def register_and_login(client, email: str, name: str = "Test User") -> dict:
    """Регистрирует пользователя, входит и возвращает его id и заголовки с токеном."""
    # client — виртуальный клиент из фикстуры client
    # email  — например "owner@example.com"
    # name   — например "Owner"
    password = "very-strong-password-123"

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
    #                    "timezone": "UTC", "created_at": "2026-10-22T..."}
    assert response.status_code == 201, response.text
    user_id = response.json()["id"]  # 1

    response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    # response.json() → {"access_token": "eyJhbGciOi...", "token_type": "bearer"}
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]  # "eyJhbGciOi..."

    # Возвращаем: {"id": 1, "headers": {"Authorization": "Bearer eyJhbGciOi..."}}
    return {"id": user_id, "headers": {"Authorization": f"Bearer {token}"}}