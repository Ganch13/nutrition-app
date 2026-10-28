"""Эндпоинты входа и сессий (шаги 72): регистрация, вход, обновление сессии, выход, смена пароля.

Как устроена сессия:
  * вход (/auth/login) возвращает короткоживущий access-токен в теле ответа и кладёт долгоживущий refresh-токен
    в HttpOnly-cookie. Скрипты страницы такой cookie прочитать не могут, поэтому украсть его через
    уязвимость в странице нельзя;
  * когда access-токен истёк (через 15 минут), интерфейс вызывает /auth/refresh — браузер сам прикладывает cookie,
    сервер выдаёт новый access-токен и заменяет refresh-токен на новый;
  * выход (/auth/logout) гасит сессию на сервере и удаляет cookie.
"""

from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from account_services import delete_account, preview_account_deletion, remove_files
from auth_services import (
    REFRESH_TOKEN_DAYS,
    InvalidRefreshTokenError,
    SamePasswordError,
    WrongPasswordError,
    change_password,
    issue_refresh_token,
    revoke_session,
    rotate_refresh_token,
)
from config import cookie_secure, get_cors_origins, get_refresh_cookie_path, registration_open
from database import get_db
from models import User
from rate_limit import (
    ACCOUNT_DELETE_BY_USER,
    LOGIN_BY_ACCOUNT,
    LOGIN_BY_ADDRESS,
    PASSWORD_CHANGE_BY_USER,
    REFRESH_BY_ADDRESS,
    REGISTER_BY_ADDRESS,
    client_address,
)
from schemas import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    DeletionPreviewResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from security import get_current_user, issue_access_token
from services import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    authenticate_user as authenticate_user_service,
    register_user as register_user_service,
)

REFRESH_COOKIE_NAME = "refresh_token"


def require_trusted_origin(request: Request) -> None:
    """Защита от подделки запросов с чужих сайтов (CSRF) для адресов, работающих с cookie сессии.

    Браузер сам указывает в заголовке Origin, с какого сайта отправлен запрос, и страница не может это подделать.
    Запрос пропускается, если Origin не указан (приложения, curl, тесты), совпадает с адресом самого сайта
    (заголовок Host) или есть в списке CORS_ORIGINS. Пример: Origin "https://evil.example" → 403.
    Вторая линия защиты — cookie с SameSite=Strict, которую браузер не отправляет с чужих сайтов.
    """
    origin = request.headers.get("origin")
    if origin is None:
        return
    origin = origin.rstrip("/")
    if origin in get_cors_origins():
        return
    host = request.headers.get("host", "")
    if host and urlparse(origin).netloc == host:
        return
    raise HTTPException(status_code=403, detail="Запрос с неизвестного сайта отклонён")


def set_refresh_cookie(response: Response, raw_token: str) -> None:
    """Кладёт refresh-токен в cookie: HttpOnly (недоступна скриптам), SameSite=Strict, Secure в production."""
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_token,
        max_age=REFRESH_TOKEN_DAYS * 24 * 60 * 60,
        path=get_refresh_cookie_path(),
        httponly=True,
        secure=cookie_secure(),
        samesite="strict",
    )


def clear_refresh_cookie(response: Response) -> None:
    """Просит браузер удалить cookie сессии (параметры должны совпадать с теми, с которыми cookie выдавалась)."""
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=get_refresh_cookie_path(),
        httponly=True,
        secure=cookie_secure(),
        samesite="strict",
    )


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=201)
def register_user_endpoint(
    registration_data: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Регистрирует пользователя. Не больше 20 попыток в час с одного адреса.

    Запрос: {"name": "Даня", "email": "danya@example.com", "password": "очень-длинный-пароль-1", "height_cm": 180}
    Ответ 201: профиль пользователя. Если email занят — 409; если регистрация закрыта (REGISTRATION_OPEN=false) — 403.
    """
    if not registration_open():
        raise HTTPException(
            status_code=403,
            detail="Регистрация закрыта. Попросите владельца сервера открыть её на время.",
        )

    address = client_address(request)
    REGISTER_BY_ADDRESS.check(address)
    # Считаем каждую попытку, в том числе неудачную: иначе перебором можно выяснять, какие email заняты
    REGISTER_BY_ADDRESS.hit(address)

    try:
        return register_user_service(db=db, registration_data=registration_data)
    except EmailAlreadyRegisteredError:
        raise HTTPException(status_code=409, detail="Этот Email уже зарегистрирован") from None


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(require_trusted_origin)])
def login_user(
    login_data: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Проверяет email и пароль. Ответ: access-токен в теле и refresh-токен в cookie.

    Защита от подбора пароля: 5 неудач на один email с одного адреса за 15 минут и 30 неудач с одного адреса
    на любые email; затем ответ 429 с заголовком Retry-After.

    Запрос: {"email": "danya@example.com", "password": "очень-длинный-пароль-1"}
    Ответ 200: {"access_token": "eyJhbGciOi...", "token_type": "bearer"} и заголовок Set-Cookie: refresh_token=...
    """
    address = client_address(request)
    account_key = f"{address}|{str(login_data.email).strip().lower()}"

    LOGIN_BY_ADDRESS.check(address)
    LOGIN_BY_ACCOUNT.check(account_key)

    try:
        user = authenticate_user_service(db=db, login_data=login_data)
    except InvalidCredentialsError:
        LOGIN_BY_ADDRESS.hit(address)
        LOGIN_BY_ACCOUNT.hit(account_key)
        raise HTTPException(
            status_code=401,
            detail="Неправильный email или password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    # Верный вход прощает прежние неудачи (человек просто опечатался)
    LOGIN_BY_ACCOUNT.reset(account_key)

    set_refresh_cookie(response, issue_refresh_token(db, user.id))
    return TokenResponse(access_token=issue_access_token(user), token_type="bearer")


@router.post("/refresh", response_model=TokenResponse, dependencies=[Depends(require_trusted_origin)])
def refresh_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    refresh_token: Annotated[str | None, Cookie()] = None,
):
    """Обменивает refresh-токен из cookie на новый access-токен (и новый refresh-токен).

    Запрос: POST /auth/refresh без тела; браузер сам прикладывает cookie.
    Ответ 200: {"access_token": "eyJhbGciOi...", "token_type": "bearer"}.
    Ответ 401: сессии нет, она просрочена или погашена — нужно войти заново (cookie при этом удаляется).
    Повторное предъявление уже заменённого токена спустя больше 10 секунд считается кражей: гасится вся сессия.
    """
    address = client_address(request)
    REFRESH_BY_ADDRESS.check(address)
    REFRESH_BY_ADDRESS.hit(address)

    try:
        user, new_refresh_token = rotate_refresh_token(db, refresh_token)
    except InvalidRefreshTokenError:
        # Ошибка вместе с удалением cookie: исключение HTTPException потеряло бы заголовки ответа
        failure = JSONResponse(
            status_code=401,
            content={"detail": "Сессия истекла. Войдите снова."},
            headers={"WWW-Authenticate": "Bearer"},
        )
        clear_refresh_cookie(failure)
        return failure

    # new_refresh_token равен None, если соседняя вкладка только что обновила эту же сессию:
    # браузер уже получил новую cookie, менять её второй раз не нужно
    if new_refresh_token is not None:
        set_refresh_cookie(response, new_refresh_token)
    return TokenResponse(access_token=issue_access_token(user), token_type="bearer")


@router.post("/logout", status_code=204, dependencies=[Depends(require_trusted_origin)])
def logout(
    db: Session = Depends(get_db),
    refresh_token: Annotated[str | None, Cookie()] = None,
):
    """Завершает сессию на этом устройстве: гасит refresh-токен и удаляет cookie. Всегда 204, даже без сессии."""
    revoke_session(db, refresh_token)
    response = Response(status_code=204)
    clear_refresh_cookie(response)
    return response


@router.post("/change-password", response_model=TokenResponse, dependencies=[Depends(require_trusted_origin)])
def change_password_endpoint(
    data: ChangePasswordRequest,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Меняет пароль. Все сессии и токены на других устройствах перестают работать, на этом открывается новая.

    Не больше 5 неверных «текущих паролей» за 15 минут: иначе украденный токен позволил бы подбирать пароль.

    Запрос: {"current_password": "старый-пароль-123", "new_password": "новый-длинный-пароль-456"}
    Ответ 200: новый access-токен (как при входе) и новая cookie сессии.
    Ошибки: 403 — текущий пароль неверен; 422 — новый пароль совпадает со старым или короче 12 символов.
    """
    limit_key = str(current_user.id)
    PASSWORD_CHANGE_BY_USER.check(limit_key)

    try:
        refresh_token = change_password(db, current_user, data.current_password, data.new_password)
    except WrongPasswordError:
        PASSWORD_CHANGE_BY_USER.hit(limit_key)
        # Не 401: интерфейс на 401 пытается обновить сессию, а здесь сессия в порядке, неверен лишь пароль
        raise HTTPException(status_code=403, detail="Текущий пароль указан неверно") from None
    except SamePasswordError:
        raise HTTPException(status_code=422, detail="Новый пароль должен отличаться от текущего") from None

    PASSWORD_CHANGE_BY_USER.reset(limit_key)
    set_refresh_cookie(response, refresh_token)
    db.refresh(current_user)
    return TokenResponse(access_token=issue_access_token(current_user), token_type="bearer")


@router.get("/delete-account/preview", response_model=DeletionPreviewResponse)
def delete_account_preview_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Показывает, что произойдёт при удалении аккаунта, ничего не меняя.

    Ответ, например: {"email": "danya@example.com", "households_to_delete": [],
    "households_to_leave": [{"id": 1, "name": "Семья", "new_owner_name": "Леся"}],
    "counts": {"weight_records": 12, "meal_entries": 340, "training_sessions": 20,
    "progress_photos": 4, "finance_transactions": 87}}
    """
    return preview_account_deletion(db, current_user)


@router.post("/delete-account", status_code=204, dependencies=[Depends(require_trusted_origin)])
def delete_account_endpoint(
    data: DeleteAccountRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Безвозвратно удаляет аккаунт и все личные данные. Нужен пароль.

    Запрос: {"password": "very-strong-password-123"}
    Ответ 204 без тела, cookie сессии удаляется. Ошибки: 403 — пароль неверен (не больше 5 попыток за 15 минут).
    Семьи: если пользователь единственный участник, семья удаляется; если он владелец, владение переходит к
    самому давнему администратору или участнику (см. GET /auth/delete-account/preview).
    Можно ли использовать тот же email снова: да, регистрация после удаления открыта как для нового человека.
    """
    limit_key = str(current_user.id)
    ACCOUNT_DELETE_BY_USER.check(limit_key)

    try:
        photo_files = delete_account(db, current_user, data.password)
    except WrongPasswordError:
        ACCOUNT_DELETE_BY_USER.hit(limit_key)
        raise HTTPException(status_code=403, detail="Пароль указан неверно") from None

    ACCOUNT_DELETE_BY_USER.reset(limit_key)
    # Файлы фото стираем после того, как база подтвердила удаление
    remove_files(photo_files)

    response = Response(status_code=204)
    clear_refresh_cookie(response)
    return response
