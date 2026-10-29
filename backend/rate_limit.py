"""Ограничение частоты запросов (шаг 72): защита от подбора паролей и массовых регистраций.

Принцип «скользящего окна»: для каждого ключа (например, "login:203.0.113.5:danya@example.com")
запоминаем моменты последних попыток. Если за последние window секунд их набралось limit —
следующие запросы блокируются, пока самая старая попытка не выйдет из окна.

Ограничитель хранится в памяти процесса. Для одного сервера с одним процессом uvicorn этого достаточно;
при нескольких процессах лимит у каждого свой (нужно вынести счётчики в Redis).
"""

import threading
import time
from collections import deque

from fastapi import HTTPException, Request

from config import trust_proxy_headers


class RateLimiter:
    """Скользящее окно: не больше limit попыток за window секунд на один ключ.

    Пример: RateLimiter("вход", limit=5, window=900) — пять неудачных входов за 15 минут.
    """

    # Сколько ключей храним максимум; при переполнении удаляем устаревшие, чтобы память не росла
    MAX_KEYS = 20_000

    def __init__(self, name: str, limit: int, window: float, clock=time.monotonic):
        self.name = name
        self.limit = limit
        self.window = window
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        """Убирает из ключа попытки старше окна и возвращает оставшиеся."""
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        return hits

    def retry_after(self, key: str) -> int:
        """Через сколько секунд можно повторить; 0 — можно прямо сейчас. Пример: 540."""
        with self._lock:
            now = self._clock()
            hits = self._prune(key, now)
            if len(hits) < self.limit:
                if not hits:
                    self._hits.pop(key, None)
                return 0
            return max(1, int(hits[0] + self.window - now) + 1)

    def hit(self, key: str) -> None:
        """Записывает попытку."""
        with self._lock:
            now = self._clock()
            if len(self._hits) >= self.MAX_KEYS:
                self._cleanup(now)
            self._prune(key, now).append(now)

    def reset(self, key: str) -> None:
        """Сбрасывает счётчик ключа (например, после успешного входа)."""
        with self._lock:
            self._hits.pop(key, None)

    def clear(self) -> None:
        """Сбрасывает все счётчики (для тестов)."""
        with self._lock:
            self._hits.clear()

    def _cleanup(self, now: float) -> None:
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= now - self.window]:
            del self._hits[key]

    def check(self, key: str) -> None:
        """Бросает ответ 429 «слишком часто», если лимит исчерпан."""
        wait = self.retry_after(key)
        if wait:
            minutes = max(1, round(wait / 60))
            raise HTTPException(
                status_code=429,
                detail=f"Слишком много попыток. Повторите примерно через {minutes} мин.",
                headers={"Retry-After": str(wait)},
            )


# Неудачные входы с одного адреса для одного email: подбор пароля к конкретному аккаунту
LOGIN_BY_ACCOUNT = RateLimiter("вход (аккаунт)", limit=5, window=15 * 60)
# Все неудачные входы с одного адреса: перебор многих аккаунтов
LOGIN_BY_ADDRESS = RateLimiter("вход (адрес)", limit=30, window=15 * 60)
# Регистрации с одного адреса
REGISTER_BY_ADDRESS = RateLimiter("регистрация", limit=20, window=60 * 60)
# Обновления сессии с одного адреса
REFRESH_BY_ADDRESS = RateLimiter("обновление сессии", limit=60, window=60)
# Неверные «текущие пароли» при смене пароля, для одного пользователя
PASSWORD_CHANGE_BY_USER = RateLimiter("смена пароля", limit=5, window=15 * 60)
# Неверные пароли при удалении аккаунта, для одного пользователя
ACCOUNT_DELETE_BY_USER = RateLimiter("удаление аккаунта", limit=5, window=15 * 60)
# Быстрое добавление с iPhone: запросы по одному личному ключу (ключ — id ключа в базе, не сам ключ)
QUICK_BY_KEY = RateLimiter("быстрое добавление (ключ)", limit=30, window=60)
# Быстрое добавление с одного адреса, считая и запросы с неверным ключом: защита от перебора ключей
QUICK_BY_ADDRESS = RateLimiter("быстрое добавление (адрес)", limit=60, window=60)

ALL_LIMITERS = (
    LOGIN_BY_ACCOUNT,
    LOGIN_BY_ADDRESS,
    REGISTER_BY_ADDRESS,
    REFRESH_BY_ADDRESS,
    PASSWORD_CHANGE_BY_USER,
    ACCOUNT_DELETE_BY_USER,
    QUICK_BY_KEY,
    QUICK_BY_ADDRESS,
)


def reset_all_limits() -> None:
    """Сбрасывает все ограничители (нужно тестам, чтобы они не влияли друг на друга)."""
    for limiter in ALL_LIMITERS:
        limiter.clear()


def client_address(request: Request) -> str:
    """Адрес клиента для ограничителей. Пример: "203.0.113.5".

    За прокси (Caddy) реальный адрес приходит в X-Forwarded-For. Берём самое правое значение — его
    дописал наш прокси; левые значения клиент мог подделать. Заголовку верим только при
    TRUST_PROXY_HEADERS=true, иначе любой клиент обошёл бы лимит, присылая разные адреса.
    """
    if trust_proxy_headers():
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded.strip():
            return forwarded.split(",")[-1].strip()[:64]
    return request.client.host if request.client else "unknown"
