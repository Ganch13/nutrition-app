from config import parse_origins

# Адрес, который мы считаем «своим» frontend (совпадает с conftest.py)
ALLOWED_ORIGIN = "http://localhost:3000"

# Адрес чужого сайта, которому доступ запрещён
FOREIGN_ORIGIN = "http://evil.example"


def test_parse_origins_cleans_input():
    """Лишние пробелы, пустые элементы и завершающий «/» убираются."""
    # raw — строка, как её можно написать в .env с лишними символами
    raw = " http://localhost:3000/ , http://127.0.0.1:3000,, "

    # result → ["http://localhost:3000", "http://127.0.0.1:3000"]
    result = parse_origins(raw)

    assert result == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_parse_origins_empty_string_gives_empty_list():
    """Пустая настройка означает «никому не разрешено», а не ошибку."""
    assert parse_origins("") == []


def test_preflight_allowed_for_frontend_origin(client):
    """Предварительный запрос от нашего frontend получает разрешение."""
    # Эти заголовки браузер сам отправляет перед запросом GET с токеном
    request_headers = {
        "Origin": ALLOWED_ORIGIN,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization",
    }

    response = client.options("/users/me", headers=request_headers)

    # 200 — «можно». В заголовке ответа сервер называет разрешённый origin
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN

    # В списке разрешённых заголовков есть Authorization (с токеном)
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed_headers

    # Cookie мы не используем, поэтому разрешение на передачу учётных
    # данных не выдаётся
    assert "access-control-allow-credentials" not in response.headers


def test_preflight_rejected_for_foreign_origin(client):
    """Предварительный запрос с чужого сайта отклоняется."""
    request_headers = {
        "Origin": FOREIGN_ORIGIN,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization",
    }

    response = client.options("/users/me", headers=request_headers)

    # 400 — «такому origin нельзя»; заголовка с разрешением нет
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_normal_request_from_frontend_gets_cors_header(client):
    """Обычный ответ для нашего frontend содержит разрешающий заголовок."""
    # /hello — открытый эндпоинт, для него токен не нужен
    response = client.get("/hello", headers={"Origin": ALLOWED_ORIGIN})

    assert response.status_code == 200
    # Без этого заголовка браузер не отдал бы ответ коду страницы
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


def test_normal_request_from_foreign_origin_gets_no_cors_header(client):
    """Для чужого origin разрешающего заголовка в ответе нет."""
    response = client.get("/hello", headers={"Origin": FOREIGN_ORIGIN})

    # Сервер ответил, но браузер из-за отсутствия заголовка скроет ответ
    # от страницы чужого сайта
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers