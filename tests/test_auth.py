def build_registration_data(**overrides) -> dict:
    """Собирает корректное тело запроса для POST /auth/register.

    Зачем нужна функция: в каждом тесте нужно менять только одно поле, а
    остальные должны оставаться правильными. Не нужно каждый раз
    переписывать весь словарь.

    Параметр **overrides принимает любые именованные аргументы. В самой
    функции это обычный словарь. Например, вызов
        build_registration_data(timezone="Not/AZone")
    даёт overrides == {"timezone": "Not/AZone"}.

    Результат вызова build_registration_data(timezone="Not/AZone"):
        {
            "name": "Test User",
            "email": "tz@example.com",
            "password": "very-strong-password-123",
            "height_cm": 180,
            "birth_date": "1990-05-17",
            "timezone": "Not/AZone",   # значение из overrides заменило исходное
        }
    """
    # Корректные значения по умолчанию, их принимает RegisterRequest:
    # пароль длиннее 12 символов, рост в допустимых пределах, зона существует.
    data = {
        "name": "Test User",
        "email": "tz@example.com",
        "password": "very-strong-password-123",
        "height_cm": 180,
        "birth_date": "1990-05-17",
        "timezone": "Europe/Berlin",
    }

    # update() перезаписывает ключи словаря значениями из overrides.
    # Если overrides пустой, словарь остаётся как есть.
    data.update(overrides)

    # Возвращаем готовое тело запроса
    return data


def test_register_rejects_unknown_timezone(client):
    """Регистрация с несуществующей зоной и датой рождения должна давать 422.

    Дату рождения оставляем намеренно: именно с ней UserResponse вызывает
    ZoneInfo(...). До исправления такой запрос сохранял пользователя, а потом
    падал с 500.
    """
    # data → {"name": "Test User", ..., "birth_date": "1990-05-17",
    #         "timezone": "Not/AZone"}
    data = build_registration_data(timezone="Not/AZone")

    # Отправляем POST-запрос на регистрацию, как это сделал бы клиент
    response = client.post("/auth/register", json=data)

    # 422 Unprocessable Entity значит, что данные не прошли проверку Pydantic
    assert response.status_code == 422, response.text

    # response.json() → {"detail": [{"type": "value_error",
    #                                "loc": ["body", "timezone"],
    #                                "msg": "Value error, Use a valid IANA timezone, ...",
    #                                "input": "Not/AZone", ...}]}
    # detail — список ошибок, [0] — первая из них, ["loc"] — путь к полю,
    # [-1] — последний элемент пути, то есть имя поля. Проверяем, что 422
    # вызвана именно полем timezone, а не другим полем запроса.
    assert response.json()["detail"][0]["loc"][-1] == "timezone"


def test_register_rejects_unknown_timezone_without_birth_date(client):
    """Неверная зона отклоняется и когда даты рождения нет.

    До исправления такой запрос проходил с кодом 201 и тихо сохранял
    «испорченную» зону. Позже она ломала дневную сводку питания.
    """
    # Начинаем с корректных данных и подставляем неверную зону
    data = build_registration_data(timezone="Not/AZone")

    # pop("birth_date") удаляет ключ из словаря. Теперь data не содержит
    # birth_date: {"name": ..., "email": ..., "password": ..., "height_cm": 180,
    #              "timezone": "Not/AZone"}
    data.pop("birth_date")

    response = client.post("/auth/register", json=data)

    # Ожидаем 422: зона проверяется независимо от даты рождения
    assert response.status_code == 422, response.text


def test_rejected_registration_does_not_create_user(client):
    """После отклонённой регистрации email остаётся свободным.

    Проверяем главное последствие ошибки: аккаунт не должен «застревать».
    """
    # Первая попытка с неверной зоной; ожидаем отказ
    bad_data = build_registration_data(timezone="Not/AZone")
    response = client.post("/auth/register", json=bad_data)
    assert response.status_code == 422, response.text

    # Вторая попытка с тем же email, но с корректной зоной "Europe/Berlin".
    # good_data → {"name": "Test User", "email": "tz@example.com", ...,
    #              "timezone": "Europe/Berlin"}
    good_data = build_registration_data()
    response = client.post("/auth/register", json=good_data)

    # Если пользователь всё же был создан первой попыткой, здесь будет 409
    assert response.status_code == 201, response.text

    # body → {"id": 1, "name": "Test User", "age": 36, "birth_date": "1990-05-17",
    #         "sex": None, ..., "timezone": "Europe/Berlin", "created_at": "..."}
    body = response.json()
    assert body["timezone"] == "Europe/Berlin"

    # Возраст вычисляется по дате рождения и зоне пользователя. Точное число
    # зависит от сегодняшней даты, поэтому проверяем только то, что это целое число
    assert isinstance(body["age"], int)


def test_register_without_timezone_uses_utc(client):
    """Если зона не передана, берётся значение по умолчанию "UTC".

    Защита от побочного эффекта: новая проверка не должна ломать
    регистрацию без этого поля.
    """
    data = build_registration_data()

    # Убираем timezone из запроса; в data его больше нет
    data.pop("timezone")

    response = client.post("/auth/register", json=data)
    assert response.status_code == 201, response.text

    # response.json()["timezone"] → "UTC" (значение по умолчанию из RegisterRequest)
    assert response.json()["timezone"] == "UTC"