"""Шаг 72. Сессии входа: refresh-токен в cookie, обновление, выход, смена пароля, защита от подбора пароля.

В тестах «браузером» служит TestClient: он, как и браузер, запоминает cookie, которые выдал сервер,
и сам прикладывает их к следующим запросам.
"""

import hashlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import services
from main import app
from models import RefreshToken
from security import ALGORITHM, SECRET_KEY, create_access_token
from tests.helpers import register_and_login

PASSWORD = "very-strong-password-123"
NEW_PASSWORD = "another-strong-password-456"


@pytest.fixture()
def db(engine):
    """Сессия базы для прямой проверки и подмены записей (например, «состарить» токен)."""
    with Session(engine) as session:
        yield session


@contextmanager
def another_device():
    """Второй «браузер» со своими cookie: например, телефон Дани рядом с его компьютером."""
    with TestClient(app) as device:
        yield device


def login(client, email="a@example.com", password=PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def cookie_value(client) -> str | None:
    """Значение cookie сессии в «браузере» или None."""
    return client.cookies.get("refresh_token")


def bearer(response) -> dict[str, str]:
    """Заголовок Authorization из ответа входа/обновления."""
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def sha(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------- вход и cookie


def test_login_sets_http_only_strict_cookie(client):
    register_and_login(client, "a@example.com")
    client.cookies.clear()

    response = login(client)
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"

    set_cookie = response.headers["set-cookie"].lower()
    assert set_cookie.startswith("refresh_token=")
    assert "httponly" in set_cookie  # скрипты страницы cookie не видят
    assert "samesite=strict" in set_cookie  # с чужих сайтов браузер её не отправит
    assert "path=/auth" in set_cookie  # уходит только на адреса /auth/...
    assert "max-age=2592000" in set_cookie  # 30 дней
    assert "secure" not in set_cookie  # в разработке по http; в production включается (см. test_hardening)

    # В теле ответа refresh-токена нет: он только в cookie
    assert "refresh" not in response.text.lower()


def test_database_stores_only_hash_of_refresh_token(client, db):
    user = register_and_login(client, "a@example.com")
    raw = cookie_value(client)
    assert raw and len(raw) >= 60

    rows = db.scalars(select(RefreshToken).where(RefreshToken.user_id == user["id"])).all()
    assert len(rows) == 1
    assert rows[0].token_hash == sha(raw)
    assert raw not in (rows[0].token_hash, rows[0].family_id)
    assert rows[0].revoked_at is None
    assert rows[0].expires_at - datetime.now(timezone.utc) > timedelta(days=29)


def test_access_token_lives_fifteen_minutes(client):
    register_and_login(client, "a@example.com")
    token = login(client).json()["access_token"]
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    remaining = datetime.fromtimestamp(payload["exp"], timezone.utc) - datetime.now(timezone.utc)
    assert timedelta(minutes=14) < remaining <= timedelta(minutes=15)


def test_failed_login_sets_no_cookie(client):
    register_and_login(client, "a@example.com")
    client.cookies.clear()
    response = login(client, password="wrong-password-123")
    assert response.status_code == 401
    assert "set-cookie" not in response.headers


def test_unknown_email_and_wrong_password_look_identical(client):
    register_and_login(client, "a@example.com")
    unknown = login(client, "nobody@example.com")
    wrong = login(client, "a@example.com", "wrong-password-123")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_password_is_verified_even_for_unknown_email(client, monkeypatch):
    """Время ответа не должно выдавать, зарегистрирован ли email: медленная проверка пароля идёт всегда."""
    register_and_login(client, "a@example.com")
    calls = []
    real = services.verify_password

    def spy(password, hashed):
        calls.append(hashed)
        return real(password, hashed)

    monkeypatch.setattr(services, "verify_password", spy)
    assert login(client, "nobody@example.com").status_code == 401
    assert len(calls) == 1  # проверка выполнена, хотя пользователя нет

    assert login(client, "a@example.com", "wrong-password-123").status_code == 401
    assert len(calls) == 2


# ---------------------------------------------------------------- обновление сессии


def test_refresh_issues_new_access_token_and_rotates_cookie(client):
    register_and_login(client, "a@example.com")
    old_cookie = cookie_value(client)

    response = client.post("/auth/refresh")
    assert response.status_code == 200, response.text
    assert client.get("/users/me", headers=bearer(response)).status_code == 200

    new_cookie = cookie_value(client)
    assert new_cookie and new_cookie != old_cookie  # токен заменён новым


def test_rotation_keeps_one_family_and_marks_old_as_rotated(client, db):
    user = register_and_login(client, "a@example.com")
    client.post("/auth/refresh")
    client.post("/auth/refresh")

    rows = db.scalars(select(RefreshToken).where(RefreshToken.user_id == user["id"]).order_by(RefreshToken.id)).all()
    assert len(rows) == 3
    assert len({row.family_id for row in rows}) == 1
    assert [row.revoked_reason for row in rows] == ["rotated", "rotated", None]


def test_refresh_without_cookie_is_rejected_and_clears_cookie(client):
    response = client.post("/auth/refresh")
    assert response.status_code == 401
    assert "refresh_token=" in response.headers["set-cookie"]
    assert "max-age=0" in response.headers["set-cookie"].lower()


def test_refresh_with_garbage_cookie_is_rejected(client):
    client.cookies.set("refresh_token", "x" * 64, path="/auth")
    assert client.post("/auth/refresh").status_code == 401


def test_refresh_with_expired_token_is_rejected(client, db):
    user = register_and_login(client, "a@example.com")
    row = db.scalars(select(RefreshToken).where(RefreshToken.user_id == user["id"])).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    assert client.post("/auth/refresh").status_code == 401


def test_double_refresh_within_grace_window_is_tolerated(client):
    """Две вкладки одновременно обновили сессию: вторая получает доступ и не вылетает из приложения."""
    register_and_login(client, "a@example.com")
    stale = cookie_value(client)
    assert client.post("/auth/refresh").status_code == 200
    fresh = cookie_value(client)

    # вторая вкладка предъявляет прежнюю cookie
    client.cookies.set("refresh_token", stale, path="/auth")
    response = client.post("/auth/refresh")
    assert response.status_code == 200
    assert "set-cookie" not in response.headers  # новую cookie не выдаём, у браузера она уже есть

    # сессия не потеряна: свежий токен по-прежнему работает
    client.cookies.set("refresh_token", fresh, path="/auth")
    assert client.post("/auth/refresh").status_code == 200


def test_reuse_of_rotated_token_after_grace_revokes_whole_session(client, db):
    """Украденный и уже заменённый токен: сессия гасится целиком, и у вора, и у владельца."""
    user = register_and_login(client, "a@example.com")
    stolen = cookie_value(client)
    assert client.post("/auth/refresh").status_code == 200
    current = cookie_value(client)

    # «Состариваем» момент замены: прошло больше 10 секунд
    old_row = db.scalars(select(RefreshToken).where(RefreshToken.token_hash == sha(stolen))).one()
    old_row.revoked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.commit()

    client.cookies.set("refresh_token", stolen, path="/auth")
    assert client.post("/auth/refresh").status_code == 401

    # честный владелец тоже потерял сессию и входит заново
    client.cookies.set("refresh_token", current, path="/auth")
    assert client.post("/auth/refresh").status_code == 401
    reasons = {row.revoked_reason for row in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user["id"]))}
    assert reasons == {"rotated", "reuse"}

    # а повторный вход работает
    assert login(client).status_code == 200


def test_reuse_detection_revokes_only_the_affected_session(client, db):
    """Кража токена на ноутбуке гасит сессию ноутбука, но не телефон того же человека."""
    register_and_login(client, "a@example.com")
    with another_device() as phone:
        assert login(phone).status_code == 200

        stolen = cookie_value(client)
        assert client.post("/auth/refresh").status_code == 200
        row = db.scalars(select(RefreshToken).where(RefreshToken.token_hash == sha(stolen))).one()
        row.revoked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()

        client.cookies.set("refresh_token", stolen, path="/auth")
        assert client.post("/auth/refresh").status_code == 401
        assert phone.post("/auth/refresh").status_code == 200


# ---------------------------------------------------------------- выход


def test_logout_revokes_session_and_clears_cookie(client):
    register_and_login(client, "a@example.com")
    saved = cookie_value(client)

    response = client.post("/auth/logout")
    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert cookie_value(client) is None

    # даже если cookie осталась у вора, обновить сессию нельзя
    client.cookies.set("refresh_token", saved, path="/auth")
    assert client.post("/auth/refresh").status_code == 401


def test_logout_is_idempotent_and_needs_no_session(client):
    assert client.post("/auth/logout").status_code == 204
    register_and_login(client, "a@example.com")
    assert client.post("/auth/logout").status_code == 204
    assert client.post("/auth/logout").status_code == 204


def test_logout_on_one_device_keeps_other_device(client):
    register_and_login(client, "a@example.com")
    with another_device() as phone:
        assert login(phone).status_code == 200

        client.post("/auth/logout")
        assert client.post("/auth/refresh").status_code == 401
        assert phone.post("/auth/refresh").status_code == 200


def test_logout_revokes_whole_chain_of_rotations(client, db):
    user = register_and_login(client, "a@example.com")
    client.post("/auth/refresh")
    client.post("/auth/refresh")
    client.post("/auth/logout")

    rows = db.scalars(select(RefreshToken).where(RefreshToken.user_id == user["id"])).all()
    assert all(row.revoked_at is not None for row in rows)
    assert [row.revoked_reason for row in rows].count("logout") == 1


def test_old_sessions_are_cleaned_up_on_next_login(client, db):
    user = register_and_login(client, "a@example.com")
    row = db.scalars(select(RefreshToken).where(RefreshToken.user_id == user["id"])).one()
    old_id = row.id
    row.expires_at = datetime.now(timezone.utc) - timedelta(days=8)
    db.commit()

    assert login(client).status_code == 200
    ids = {r.id for r in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user["id"]))}
    assert old_id not in ids and len(ids) == 1


# ---------------------------------------------------------------- токены доступа


def test_access_token_without_password_fingerprint_is_rejected(client):
    user = register_and_login(client, "a@example.com")
    bare = create_access_token({"sub": str(user["id"])})
    assert client.get("/users/me", headers={"Authorization": f"Bearer {bare}"}).status_code == 401

    wrong = create_access_token({"sub": str(user["id"]), "pv": "0000000000000000"})
    assert client.get("/users/me", headers={"Authorization": f"Bearer {wrong}"}).status_code == 401

    not_text = create_access_token({"sub": str(user["id"]), "pv": 12345})
    assert client.get("/users/me", headers={"Authorization": f"Bearer {not_text}"}).status_code == 401

    non_ascii = create_access_token({"sub": str(user["id"]), "pv": "пароль"})
    assert client.get("/users/me", headers={"Authorization": f"Bearer {non_ascii}"}).status_code == 401


# ---------------------------------------------------------------- смена пароля


def change(client, headers, current=PASSWORD, new=NEW_PASSWORD):
    return client.post(
        "/auth/change-password",
        json={"current_password": current, "new_password": new},
        headers=headers,
    )


def test_change_password_signs_out_other_devices_but_not_this_one(client):
    user = register_and_login(client, "a@example.com")
    old_access = user["headers"]
    with another_device() as phone:
        phone_login = login(phone)
        assert phone_login.status_code == 200

        response = change(client, old_access)
        assert response.status_code == 200, response.text
        new_access = bearer(response)

        # этот браузер продолжает работать с новым токеном и новой cookie
        assert client.get("/users/me", headers=new_access).status_code == 200
        assert client.post("/auth/refresh").status_code == 200

        # старый токен доступа перестал действовать сразу, не через 15 минут
        assert client.get("/users/me", headers=old_access).status_code == 401
        assert phone.get("/users/me", headers=bearer(phone_login)).status_code == 401
        # телефон потерял и сессию
        assert phone.post("/auth/refresh").status_code == 401

    # вход со старым паролем невозможен, с новым возможен
    client.cookies.clear()
    assert login(client).status_code == 401
    assert login(client, password=NEW_PASSWORD).status_code == 200


def test_change_password_validation(client):
    user = register_and_login(client, "a@example.com")
    assert change(client, user["headers"], current="wrong-password-123").status_code == 403
    assert change(client, user["headers"], new=PASSWORD).status_code == 422  # совпадает со старым
    assert change(client, user["headers"], new="short").status_code == 422
    assert client.post("/auth/change-password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}).status_code == 401

    # ничего не изменилось
    client.cookies.clear()
    assert login(client).status_code == 200


def test_change_password_wrong_current_does_not_sign_out(client):
    """Неверный текущий пароль — 403, а не 401: иначе интерфейс счёл бы сессию истёкшей и разлогинил человека."""
    user = register_and_login(client, "a@example.com")
    assert change(client, user["headers"], current="wrong-password-123").status_code == 403
    assert client.get("/users/me", headers=user["headers"]).status_code == 200
    assert client.post("/auth/refresh").status_code == 200


def test_change_password_is_rate_limited(client):
    user = register_and_login(client, "a@example.com")
    for _ in range(5):
        assert change(client, user["headers"], current="wrong-password-123").status_code == 403
    blocked = change(client, user["headers"])  # даже верный пароль уже не принимается
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    # пароль не изменился
    client.cookies.clear()
    assert login(client).status_code == 200


# ---------------------------------------------------------------- ограничения частоты


def test_login_is_blocked_after_five_failures_for_account(client):
    register_and_login(client, "a@example.com")
    for _ in range(5):
        assert login(client, password="wrong-password-123").status_code == 401

    blocked = login(client)  # верный пароль, но попытки исчерпаны
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    assert "set-cookie" not in blocked.headers

    # другой email с того же адреса не заблокирован
    register_and_login(client, "b@example.com")
    assert login(client, "b@example.com").status_code == 200


def test_successful_login_resets_failure_counter(client):
    register_and_login(client, "a@example.com")
    for _ in range(4):
        assert login(client, password="wrong-password-123").status_code == 401
    assert login(client).status_code == 200
    for _ in range(4):
        assert login(client, password="wrong-password-123").status_code == 401
    assert login(client).status_code == 200


def test_login_is_blocked_after_thirty_failures_from_one_address(client):
    for index in range(30):
        assert login(client, f"nobody{index}@example.com").status_code == 401
    blocked = login(client, "another@example.com")
    assert blocked.status_code == 429


def test_failed_login_blocks_do_not_depend_on_email_case(client):
    register_and_login(client, "a@example.com")
    variants = ["a@example.com", "A@Example.com", " a@example.com", "A@EXAMPLE.COM", "a@example.COM"]
    for email in variants:
        assert login(client, email, "wrong-password-123").status_code == 401
    assert login(client, "a@example.com").status_code == 429


def test_register_is_limited_per_address(client):
    for index in range(20):
        response = client.post(
            "/auth/register",
            json={"name": f"U{index}", "email": f"u{index}@example.com", "password": PASSWORD, "height_cm": 170},
        )
        assert response.status_code == 201, (index, response.text)
    blocked = client.post(
        "/auth/register",
        json={"name": "Extra", "email": "extra@example.com", "password": PASSWORD, "height_cm": 170},
    )
    assert blocked.status_code == 429


def test_registration_can_be_closed(client, monkeypatch):
    """После регистрации всей семьи регистрацию закрывают: посторонние не заведут аккаунт, а свои входят как раньше."""
    owner = register_and_login(client, "a@example.com")
    monkeypatch.setenv("REGISTRATION_OPEN", "false")

    body = {"name": "Чужой", "email": "stranger@example.com", "password": PASSWORD, "height_cm": 170}
    response = client.post("/auth/register", json=body)
    assert response.status_code == 403
    assert "закрыта" in response.json()["detail"]

    # вход и работа существующих пользователей не затронуты
    assert login(client).status_code == 200
    assert client.get("/users/me", headers=owner["headers"]).status_code == 200
    # приглашения в семью по коду работают (пользователи уже есть)
    assert client.post("/households", json={"name": "Дом"}, headers=owner["headers"]).status_code == 201

    monkeypatch.setenv("REGISTRATION_OPEN", "true")
    assert client.post("/auth/register", json=body).status_code == 201


def test_closed_registration_does_not_use_up_the_rate_limit(client, monkeypatch):
    monkeypatch.setenv("REGISTRATION_OPEN", "0")
    body = {"name": "X", "email": "x@example.com", "password": PASSWORD, "height_cm": 170}
    for _ in range(25):
        assert client.post("/auth/register", json=body).status_code == 403
    monkeypatch.setenv("REGISTRATION_OPEN", "1")
    assert client.post("/auth/register", json=body).status_code == 201


def test_refresh_is_limited_per_address(client):
    register_and_login(client, "a@example.com")
    for _ in range(60):
        assert client.post("/auth/refresh").status_code == 200
    assert client.post("/auth/refresh").status_code == 429


def test_forwarded_header_is_ignored_unless_proxy_is_trusted(client):
    """Без доверия к прокси заголовок X-Forwarded-For подделать легко, и он не помогает обойти лимит."""
    register_and_login(client, "a@example.com")
    for index in range(5):
        response = client.post(
            "/auth/login",
            json={"email": "a@example.com", "password": "wrong-password-123"},
            headers={"X-Forwarded-For": f"203.0.113.{index}"},
        )
        assert response.status_code == 401
    blocked = client.post(
        "/auth/login",
        json={"email": "a@example.com", "password": PASSWORD},
        headers={"X-Forwarded-For": "203.0.113.99"},
    )
    assert blocked.status_code == 429


def test_forwarded_header_from_trusted_proxy_separates_clients(client, monkeypatch):
    """За Caddy у каждого посетителя свой адрес: один «злоумышленник» не блокирует вход другим."""
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    register_and_login(client, "a@example.com")

    def attempt(address, password):
        return client.post(
            "/auth/login",
            json={"email": "a@example.com", "password": password},
            headers={"X-Forwarded-For": address},
        )

    for _ in range(5):
        assert attempt("198.51.100.7", "wrong-password-123").status_code == 401
    assert attempt("198.51.100.7", PASSWORD).status_code == 429
    assert attempt("198.51.100.8", PASSWORD).status_code == 200  # другой посетитель


def test_only_rightmost_forwarded_address_counts(client, monkeypatch):
    """Левые адреса в X-Forwarded-For клиент мог дописать сам, поэтому учитывается последний (добавленный прокси)."""
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    register_and_login(client, "a@example.com")
    for index in range(5):
        response = client.post(
            "/auth/login",
            json={"email": "a@example.com", "password": "wrong-password-123"},
            headers={"X-Forwarded-For": f"10.0.0.{index}, 198.51.100.7"},
        )
        assert response.status_code == 401
    blocked = client.post(
        "/auth/login",
        json={"email": "a@example.com", "password": PASSWORD},
        headers={"X-Forwarded-For": "10.9.9.9, 198.51.100.7"},
    )
    assert blocked.status_code == 429


# ---------------------------------------------------------------- защита от запросов с чужих сайтов


@pytest.mark.parametrize("path", ["/auth/login", "/auth/refresh", "/auth/logout"])
def test_cookie_endpoints_reject_foreign_origin(client, path):
    register_and_login(client, "a@example.com")
    body = {"email": "a@example.com", "password": PASSWORD} if path == "/auth/login" else None
    response = client.post(path, json=body, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    # отклонённый запрос ничего не изменил: сессия на месте
    assert client.post("/auth/refresh").status_code == 200


def test_change_password_rejects_foreign_origin(client):
    user = register_and_login(client, "a@example.com")
    response = client.post(
        "/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers={**user["headers"], "Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    client.cookies.clear()
    assert login(client).status_code == 200  # пароль прежний


def test_cookie_endpoints_accept_own_origins(client):
    register_and_login(client, "a@example.com")
    for origin in ("http://localhost:3000", "http://localhost:3000/", "http://testserver"):
        response = client.post("/auth/refresh", headers={"Origin": origin})
        assert response.status_code == 200, origin
    # заголовок Origin "null" (песочница iframe) — чужой
    assert client.post("/auth/refresh", headers={"Origin": "null"}).status_code == 403


def test_cors_allows_credentials_only_for_own_frontend(client):
    own = client.options(
        "/auth/refresh",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )
    assert own.status_code == 200
    assert own.headers["access-control-allow-credentials"] == "true"
    assert own.headers["access-control-allow-origin"] == "http://localhost:3000"

    foreign = client.options(
        "/auth/refresh",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert foreign.status_code == 400
    # Без allow-origin браузер всё равно не отдаст ответ чужой странице
    assert "access-control-allow-origin" not in foreign.headers
