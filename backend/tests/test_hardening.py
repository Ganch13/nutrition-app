"""Шаг 72. Защита публичного сервера: заголовки безопасности, лимит размера запроса, режим production,
проверка настроек при запуске, ограничитель частоты запросов.

Часть проверок запускает приложение в отдельном процессе с ENVIRONMENT=production: режим выбирается
при запуске, и в одном процессе с остальными тестами его нельзя переключить.
"""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from starlette.requests import Request

from config import production_problems
from rate_limit import RateLimiter, client_address
from tests.helpers import register_and_login
from tests.photo_samples import JPEG_PLAIN

BACKEND_DIR = Path(__file__).resolve().parent.parent

GOOD_SECRET = "Zq8vK3mP9xLw2RtY7nBc5HdF1gJs6VaE4uXo0iNk"
GOOD_PRODUCTION = {
    "JWT_SECRET_KEY": GOOD_SECRET,
    "CORS_ORIGINS": "https://nutrition.example.org",
    "ALLOWED_HOSTS": "nutrition.example.org,localhost",
}


# ---------------------------------------------------------------- заголовки безопасности


def test_security_headers_on_every_kind_of_response(client):
    user = register_and_login(client, "a@example.com")
    responses = [
        client.get("/health"),  # успех
        client.get("/users/me"),  # 401
        client.get("/no-such-address"),  # 404
        client.get("/users/me", headers=user["headers"]),  # успех с данными
        client.post("/auth/login", json={"email": "bad"}),  # 422
    ]
    for response in responses:
        headers = response.headers
        assert headers["x-content-type-options"] == "nosniff", response.url
        assert headers["x-frame-options"] == "DENY"
        assert headers["referrer-policy"] == "no-referrer"
        assert headers["cache-control"] == "no-store"
        # Ответ API не должен выполнять скрипты и загружать ресурсы
        assert headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
        # В разработке нет HTTPS, поэтому HSTS не отправляется (иначе браузер «запомнил» бы localhost как https-only)
        assert "strict-transport-security" not in headers


def test_docs_page_keeps_swagger_working_in_development(client):
    response = client.get("/docs")
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers  # строгая политика сломала бы Swagger UI
    assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get("/openapi.json").status_code == 200


def test_photo_file_keeps_its_own_cache_policy(client):
    user = register_and_login(client, "a@example.com")
    upload = client.post(
        f"/users/{user['id']}/progress-photos",
        params={"taken_on": "2026-10-20"},
        content=JPEG_PLAIN,
        headers={**user["headers"], "Content-Type": "image/jpeg"},
    )
    assert upload.status_code == 201, upload.text
    file_response = client.get(upload.json()["url"], headers=user["headers"])
    assert file_response.status_code == 200
    assert file_response.headers["cache-control"] == "private, max-age=86400"
    assert file_response.headers["x-content-type-options"] == "nosniff"


# ---------------------------------------------------------------- лимит размера запроса


def test_declared_oversized_body_is_rejected_without_reading(client):
    response = client.post(
        "/auth/login",
        content=b"{}",
        headers={"Content-Type": "application/json", "Content-Length": str(5 * 1024 * 1024)},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "Слишком большой запрос"}


def test_garbage_content_length_is_rejected(client):
    response = client.post("/auth/login", content=b"{}", headers={"Content-Type": "application/json", "Content-Length": "abc"})
    assert response.status_code == 413


def test_oversized_body_is_rejected(client):
    body = json.dumps({"email": "a@example.com", "password": "x", "pad": "y" * (1024 * 1024)})
    response = client.post("/auth/login", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_body_without_declared_length_is_counted_while_streaming(client):
    def chunks():
        for _ in range(12):
            yield b"z" * (100 * 1024)  # 12 × 100 КБ = 1,2 МБ, размер заранее не объявлен

    response = client.post("/auth/login", content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_normal_sized_body_passes_the_limit(client):
    body = json.dumps({"email": "a@example.com", "password": "x", "pad": "y" * (500 * 1024)})
    response = client.post("/auth/login", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 401  # дошло до проверки пароля


def test_oversized_error_still_carries_cors_headers(client):
    """Иначе браузер показал бы «ошибку CORS» вместо понятного «слишком большой запрос»."""
    response = client.post(
        "/auth/login",
        content=b"{}",
        headers={
            "Origin": "http://localhost:3000",
            "Content-Type": "application/json",
            "Content-Length": str(5 * 1024 * 1024),
        },
    )
    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_photo_upload_has_larger_limit_and_own_message(client, monkeypatch):
    monkeypatch.setenv("MAX_PHOTO_MB", "1")
    user = register_and_login(client, "a@example.com")
    headers = {**user["headers"], "Content-Type": "image/jpeg"}
    url = f"/users/{user['id']}/progress-photos"

    # Чуть больше лимита фото: решает сам эндпоинт и отвечает своим сообщением о размере фото
    slightly_over = client.post(url, params={"taken_on": "2026-10-20"}, content=b"\xff\xd8" + b"0" * (1100 * 1024), headers=headers)
    assert slightly_over.status_code == 413
    assert slightly_over.json()["detail"] != "Слишком большой запрос"

    # Намного больше (лимит фото + запас 1 МБ): отсекает общая защита
    way_over = client.post(url, params={"taken_on": "2026-10-20"}, content=b"\xff\xd8" + b"0" * (3 * 1024 * 1024), headers=headers)
    assert way_over.status_code == 413
    assert way_over.json() == {"detail": "Слишком большой запрос"}


def test_get_and_delete_requests_skip_the_body_limit(client):
    user = register_and_login(client, "a@example.com")
    huge = {"Content-Length": str(50 * 1024 * 1024)}
    response = client.get("/users/me", headers={**user["headers"], **huge})
    assert response.status_code == 200


# ---------------------------------------------------------------- проверка настроек для production


def test_good_production_settings_have_no_problems():
    assert production_problems(GOOD_PRODUCTION) == []


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"JWT_SECRET_KEY": ""}, "JWT_SECRET_KEY"),
        ({"JWT_SECRET_KEY": "short-key-123"}, "короче 32"),
        ({"JWT_SECRET_KEY": "change-me-" + "x" * 40}, "заглушку"),
        ({"JWT_SECRET_KEY": "my-" + "password" + "-" + "Qw7" * 12}, "заглушку"),
        ({"CORS_ORIGINS": "http://nutrition.example.org"}, "без https"),
        ({"CORS_ORIGINS": "https://nutrition.example.org, http://localhost:3000"}, "http://localhost:3000"),
        ({"COOKIE_SECURE": "false"}, "COOKIE_SECURE"),
        ({"COOKIE_SECURE": "0"}, "COOKIE_SECURE"),
        ({"ALLOWED_HOSTS": ""}, "ALLOWED_HOSTS"),
        ({"ALLOWED_HOSTS": " , "}, "ALLOWED_HOSTS"),
        ({"ENABLE_DOCS": "true"}, "ENABLE_DOCS"),
        ({"ENABLE_DOCS": "1"}, "ENABLE_DOCS"),
    ],
)
def test_each_unsafe_production_setting_is_reported(overrides, expected):
    problems = production_problems({**GOOD_PRODUCTION, **overrides})
    assert len(problems) == 1, problems
    assert expected in problems[0]


def test_safe_explicit_values_are_not_reported():
    settings = {**GOOD_PRODUCTION, "COOKIE_SECURE": "true", "ENABLE_DOCS": "false"}
    assert production_problems(settings) == []


def test_all_problems_are_listed_together():
    # Пустые настройки: нет ключа и не задан домен (адреса CORS необязательны: сайт и API на одном домене)
    problems = production_problems({})
    assert len(problems) == 2
    assert "JWT_SECRET_KEY" in problems[0] and "ALLOWED_HOSTS" in problems[1]


# ---------------------------------------------------------------- запуск приложения в режиме production


def run_python(code: str, extra_env: dict[str, str]) -> subprocess.CompletedProcess:
    """Запускает фрагмент кода отдельным процессом в папке backend с заданными переменными окружения."""
    env = {key: value for key, value in os.environ.items() if key not in {"ENVIRONMENT", "ENABLE_DOCS", "COOKIE_SECURE", "ALLOWED_HOSTS", "TRUST_PROXY_HEADERS", "REFRESH_COOKIE_PATH"}}
    env.update(extra_env)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


PRODUCTION_PROBE = """
    import json
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app, base_url="https://nutrition.example.org")
    docs = client.get("/docs")
    redoc = client.get("/redoc")
    schema = client.get("/openapi.json")
    missing = client.get("/no-such-address")
    refresh = client.post("/auth/refresh")
    evil_host = TestClient(app, base_url="https://evil.example.net").get("/no-such-address")
    print(json.dumps({
        "docs": docs.status_code, "redoc": redoc.status_code, "schema": schema.status_code,
        "missing": missing.status_code,
        "hsts": missing.headers.get("strict-transport-security"),
        "csp": missing.headers.get("content-security-policy"),
        "refresh": refresh.status_code,
        "refresh_cookie": refresh.headers.get("set-cookie", ""),
        "evil_host": evil_host.status_code,
    }))
"""


def test_production_mode_hides_docs_adds_hsts_and_checks_host():
    result = run_python(PRODUCTION_PROBE, {**GOOD_PRODUCTION, "ENVIRONMENT": "production"})
    assert result.returncode == 0, result.stderr
    probe = json.loads(result.stdout.strip().splitlines()[-1])

    assert probe["docs"] == probe["redoc"] == probe["schema"] == 404  # документация закрыта
    assert probe["missing"] == 404
    assert probe["hsts"] == "max-age=31536000; includeSubDomains"
    assert probe["csp"] == "default-src 'none'; frame-ancestors 'none'"
    assert probe["refresh"] == 401
    assert "Secure" in probe["refresh_cookie"]  # в production cookie только по HTTPS
    assert probe["evil_host"] == 400  # чужой заголовок Host отклонён


def test_docs_can_be_switched_off_in_development_too():
    result = run_python(PRODUCTION_PROBE.replace('base_url="https://nutrition.example.org"', 'base_url="http://testserver"').replace('missing = ', 'missing = ', 1), {
        "ENVIRONMENT": "development", "ENABLE_DOCS": "false", "JWT_SECRET_KEY": "dev-key-for-this-probe-only",
    })
    assert result.returncode == 0, result.stderr
    probe = json.loads(result.stdout.strip().splitlines()[-1])
    assert probe["docs"] == probe["schema"] == 404
    assert probe["hsts"] is None  # HSTS только в production


@pytest.mark.parametrize(
    "overrides, expected_in_error",
    [
        ({"JWT_SECRET_KEY": "short"}, "JWT_SECRET_KEY"),
        ({"CORS_ORIGINS": "http://localhost:3000"}, "https"),
        ({"ALLOWED_HOSTS": ""}, "ALLOWED_HOSTS"),
        ({"ENABLE_DOCS": "true"}, "ENABLE_DOCS"),
    ],
)
def test_server_refuses_to_start_with_unsafe_production_settings(overrides, expected_in_error):
    result = run_python("import main", {**GOOD_PRODUCTION, **overrides, "ENVIRONMENT": "production"})
    assert result.returncode != 0
    assert "Небезопасные настройки" in result.stderr
    assert expected_in_error in result.stderr


def test_development_mode_starts_with_any_settings():
    result = run_python("import main; print('started')", {"JWT_SECRET_KEY": "short", "CORS_ORIGINS": "http://localhost:3000"})
    assert result.returncode == 0, result.stderr
    assert "started" in result.stdout


def test_cookie_path_follows_setting():
    code = """
        from fastapi.testclient import TestClient
        from main import app
        response = TestClient(app).post("/auth/refresh")
        print(response.headers["set-cookie"])
    """
    result = run_python(code, {"JWT_SECRET_KEY": "dev-key-for-this-probe-only", "REFRESH_COOKIE_PATH": "/api/auth"})
    assert result.returncode == 0, result.stderr
    assert "Path=/api/auth" in result.stdout


# ---------------------------------------------------------------- ограничитель частоты


class FakeClock:
    """Часы, которые стоят на месте, пока тест сам не передвинет стрелки."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make_limiter(limit=3, window=60.0):
    clock = FakeClock()
    return RateLimiter("тест", limit=limit, window=window, clock=clock), clock


def test_limiter_allows_up_to_limit_then_blocks():
    limiter, _ = make_limiter(limit=3)
    for _ in range(3):
        assert limiter.retry_after("k") == 0
        limiter.hit("k")
    assert limiter.retry_after("k") > 0


def test_limiter_window_slides():
    limiter, clock = make_limiter(limit=2, window=60)
    limiter.hit("k")
    clock.now += 30
    limiter.hit("k")
    assert limiter.retry_after("k") == 31  # первая попытка выйдет из окна через 30 с (+1 с запаса)
    clock.now += 31
    assert limiter.retry_after("k") == 0  # самая старая вышла из окна
    limiter.hit("k")
    assert limiter.retry_after("k") > 0  # вторая и новая — снова два


def test_limiter_keys_are_independent_and_resettable():
    limiter, _ = make_limiter(limit=1)
    limiter.hit("a")
    assert limiter.retry_after("a") > 0
    assert limiter.retry_after("b") == 0
    limiter.reset("a")
    assert limiter.retry_after("a") == 0


def test_limiter_check_raises_429_with_retry_after():
    from fastapi import HTTPException

    limiter, _ = make_limiter(limit=1, window=600)
    limiter.check("k")  # пока можно
    limiter.hit("k")
    with pytest.raises(HTTPException) as caught:
        limiter.check("k")
    assert caught.value.status_code == 429
    assert int(caught.value.headers["Retry-After"]) in range(595, 602)


def test_limiter_memory_is_bounded():
    limiter, clock = make_limiter(limit=1, window=10)
    limiter.MAX_KEYS = 100
    for index in range(100):
        limiter.hit(f"old-{index}")
    clock.now += 20  # все прежние попытки устарели
    for index in range(50):
        limiter.hit(f"new-{index}")
    assert len(limiter._hits) <= 60  # старые ключи вычищены, а не накапливаются бесконечно


def test_limiter_checking_does_not_record_attempts():
    limiter, _ = make_limiter(limit=1)
    for _ in range(10):
        limiter.check("k")
    assert limiter.retry_after("k") == 0


def make_request(client_host="203.0.113.5", forwarded=None):
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return Request({"type": "http", "headers": headers, "client": (client_host, 5000), "method": "GET", "path": "/"})


def test_client_address_uses_connection_address_by_default():
    assert client_address(make_request(forwarded="1.2.3.4")) == "203.0.113.5"


def test_client_address_trusts_last_forwarded_value_behind_proxy(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    assert client_address(make_request(forwarded="1.2.3.4, 198.51.100.9")) == "198.51.100.9"
    assert client_address(make_request()) == "203.0.113.5"  # заголовка нет — адрес соединения
    assert client_address(make_request(forwarded="  ")) == "203.0.113.5"
