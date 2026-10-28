"""Защитные «прослойки» между сетью и приложением (шаг 72).

Каждая прослойка — маленький ASGI-класс: получает запрос раньше эндпоинтов и может добавить заголовки
к ответу или отклонить запрос. Они не знают о бизнес-логике и работают одинаково для всех адресов.
"""

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from config import docs_enabled, get_max_photo_bytes, is_production

# Обычные запросы (JSON) значительно меньше мегабайта; всё, что больше, — ошибка или попытка забить память
DEFAULT_BODY_LIMIT = 1024 * 1024

# Запас сверху для фото: точную проверку размера и понятное сообщение даёт сам эндпоинт фото
PHOTO_BODY_MARGIN = 1024 * 1024

# Адреса документации: для них строгая политика содержимого сломала бы страницу Swagger
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


def body_limit_for(method: str, path: str) -> int:
    """Максимальный размер тела запроса. Пример: ("POST", "/auth/login") → 1048576.

    Загрузка фото прогресса (POST /users/1/progress-photos) может быть крупнее — до размера фото плюс запас.
    """
    if method == "POST" and path.endswith("/progress-photos"):
        return get_max_photo_bytes() + PHOTO_BODY_MARGIN
    return DEFAULT_BODY_LIMIT


class SecurityHeadersMiddleware:
    """Добавляет к каждому ответу заголовки, закрывающие типовые атаки в браузере.

    Пример добавленных заголовков:
        X-Content-Type-Options: nosniff        — браузер не «угадывает» тип файла (защита от подмены)
        X-Frame-Options: DENY                  — API нельзя встроить в чужую страницу (clickjacking)
        Referrer-Policy: no-referrer           — адреса не утекают на другие сайты
        Content-Security-Policy: default-src 'none'; frame-ancestors 'none'
                                               — ответ API не может выполнять скрипты и загружать ресурсы
        Cache-Control: no-store                — ответы с личными данными не оседают в кэше
        Strict-Transport-Security: ...         — только в production: браузер всегда ходит по HTTPS
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        relaxed_csp = docs_enabled() and path.startswith(DOCS_PATHS)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                if not relaxed_csp:
                    headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
                # Эндпоинты, которые сами задали кэширование (файл фото), не трогаем
                if "cache-control" not in headers:
                    headers["Cache-Control"] = "no-store"
                if is_production():
                    headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            await send(message)

        await self.app(scope, receive, send_with_headers)


class _BodyTooLarge(Exception):
    """Внутренний сигнал: тело запроса, пришедшее частями, превысило лимит."""


class BodySizeLimitMiddleware:
    """Отклоняет слишком большие тела запросов ответом 413 до того, как приложение начнёт их читать.

    Два случая:
      * клиент заявил размер в Content-Length — сравниваем сразу, тело не читаем вообще;
      * размер не заявлен (передача частями) — считаем байты по мере поступления и обрываем при превышении.
    Запросы без тела (GET, HEAD, OPTIONS, DELETE) не проверяются.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS", "DELETE"):
            await self.app(scope, receive, send)
            return

        limit = body_limit_for(scope["method"], scope.get("path", ""))
        declared = Headers(scope=scope).get("content-length")

        if declared is not None:
            try:
                too_large = int(declared) > limit
            except ValueError:
                too_large = True  # нечисловой Content-Length — заведомо некорректный запрос
            if too_large:
                await self._reject(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return

        received = 0
        exceeded = False
        started = False
        swallow = False

        async def counting_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise _BodyTooLarge
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal started, swallow
            if swallow:
                return
            if message["type"] == "http.response.start":
                if exceeded and not started:
                    # FastAPI поймал наше прерывание чтения и собрался ответить «400, не удалось разобрать тело».
                    # Подменяем этот ответ честным 413 и отбрасываем остаток его сообщений.
                    swallow = True
                    started = True
                    await self._reject(scope, receive, send)
                    return
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except _BodyTooLarge:
            if not started:
                await self._reject(scope, receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": "Слишком большой запрос"},
            headers={"Connection": "close"},
        )
        await response(scope, receive, send)
