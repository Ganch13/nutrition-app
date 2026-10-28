"""Настройки приложения, которые читаются из переменных окружения."""

import os
from collections.abc import Mapping

from dotenv import load_dotenv

# Загружаем переменные из файла .env в переменные окружения процесса.
# Вызываем здесь явно, чтобы модуль не зависел от того, кто успел
# загрузить .env раньше. Повторный вызов безопасен.
load_dotenv()


def parse_origins(raw_value: str) -> list[str]:
    """Превращает строку с адресами через запятую в чистый список.

    Аргумент:
        raw_value — строка из переменной окружения, например
                    " http://localhost:3000/ , http://127.0.0.1:3000,, "

    Результат для этого примера:
        ["http://localhost:3000", "http://127.0.0.1:3000"]
    """
    # split(",") режет строку по запятым и даёт список строк, в том числе с
    # пробелами и пустые. strip() убирает пробелы по краям. Условие
    # "if item.strip()" отбрасывает пустые элементы (после лишней запятой).
    # rstrip("/") убирает завершающую косую черту: браузер присылает origin
    # без неё, и с ней адрес не совпал бы.
    return [
        item.strip().rstrip("/")
        for item in raw_value.split(",")
        if item.strip()
    ]


def get_cors_origins() -> list[str]:
    """Возвращает адреса frontend, которым разрешено обращаться к API.

    Берутся из переменной CORS_ORIGINS. Если переменной нет, возвращается
    пустой список: безопасное значение по умолчанию, при котором
    запросы с других адресов не разрешены.

    Пример результата: ["http://localhost:3000"]
    """
    return parse_origins(os.getenv("CORS_ORIGINS", ""))

def get_upload_dir() -> str:
    """Папка для загружаемых файлов (фото прогресса). Берётся из UPLOAD_DIR, по умолчанию "uploads".

    В Docker это папка тома, поэтому файлы переживают пересборку контейнера.
    Пример результата: "/data/uploads".
    """
    return os.getenv("UPLOAD_DIR", "uploads")


def get_max_photo_bytes() -> int:
    """Максимальный размер одной фотографии в байтах. Из MAX_PHOTO_MB (по умолчанию 8 МБ).

    Пример: MAX_PHOTO_MB=8 → 8 388 608. Неверное значение (не число, меньше 1) заменяется на 8.
    """
    try:
        megabytes = int(os.getenv("MAX_PHOTO_MB", "8"))
    except ValueError:
        megabytes = 8
    return max(megabytes, 1) * 1024 * 1024


# ---------------------------------------------------------------------------
# Режим работы и безопасность публичного сервера (шаг 72)
# ---------------------------------------------------------------------------


def _flag(name: str, default: bool) -> bool:
    """Читает переменную-«выключатель»: "1", "true", "yes", "on" → True; "0", "false", "no", "off" → False."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def get_environment() -> str:
    """Режим из ENVIRONMENT: "development" (по умолчанию) или "production"."""
    return os.getenv("ENVIRONMENT", "development").strip().lower()


def is_production() -> bool:
    """True на настоящем сервере: включаются строгие проверки настроек, выключаются /docs и /openapi.json."""
    return get_environment() == "production"


def docs_enabled() -> bool:
    """Показывать ли Swagger UI (/docs). Включено при разработке, выключено в production, меняется ENABLE_DOCS."""
    return _flag("ENABLE_DOCS", not is_production())


def cookie_secure() -> bool:
    """Помечать ли cookie обновления флагом Secure (только по HTTPS). Включено в production, меняется COOKIE_SECURE."""
    return _flag("COOKIE_SECURE", is_production())


def trust_proxy_headers() -> bool:
    """Верить ли заголовку X-Forwarded-For (адрес клиента за Caddy). Включайте, только если сервер доступен лишь через прокси."""
    return _flag("TRUST_PROXY_HEADERS", False)


def registration_open() -> bool:
    """Можно ли создавать новые аккаунты (REGISTRATION_OPEN, по умолчанию да).

    На публичном сервере после регистрации всех членов семьи ставят false: тогда посторонние завести аккаунт не смогут.
    Вход существующих пользователей и приглашения в семью по коду работают как обычно.
    """
    return _flag("REGISTRATION_OPEN", True)


def get_allowed_hosts() -> list[str]:
    """Допустимые значения заголовка Host из ALLOWED_HOSTS. Пустой список — без ограничений.

    Пример: ALLOWED_HOSTS="nutrition.example.com, localhost" → ["nutrition.example.com", "localhost"].
    """
    return [item.strip() for item in os.getenv("ALLOWED_HOSTS", "").split(",") if item.strip()]


def get_refresh_cookie_path() -> str:
    """Путь, для которого браузер отправляет cookie обновления сессии (REFRESH_COOKIE_PATH, по умолчанию "/auth").

    Если API доступно по адресу с префиксом (например, https://site/api/auth/...), укажите "/api/auth".
    """
    return os.getenv("REFRESH_COOKIE_PATH", "/auth").strip() or "/auth"


# Слабые значения секретного ключа, которые нельзя оставлять на сервере
_WEAK_SECRET_MARKERS = ("change", "example", "secret", "password", "test", "default", "your")


def production_problems(env: Mapping[str, str] | None = None) -> list[str]:
    """Проверяет настройки для режима production и возвращает список проблем (пустой — всё в порядке).

    Пример результата: ["JWT_SECRET_KEY короче 32 символов", "CORS_ORIGINS содержит адрес без https: http://localhost:3000"].
    Принимает словарь настроек, чтобы проверку можно было запускать без изменения окружения процесса.
    """
    source = os.environ if env is None else env
    problems: list[str] = []

    key = source.get("JWT_SECRET_KEY", "")
    if len(key) < 32:
        problems.append("JWT_SECRET_KEY короче 32 символов (создайте: python -c \"import secrets; print(secrets.token_urlsafe(48))\")")
    elif any(marker in key.lower() for marker in _WEAK_SECRET_MARKERS):
        problems.append("JWT_SECRET_KEY похож на пример или пароль-заглушку: сгенерируйте случайный")

    for origin in parse_origins(source.get("CORS_ORIGINS", "")):
        if not origin.startswith("https://"):
            problems.append(f"CORS_ORIGINS содержит адрес без https: {origin}")

    secure_raw = source.get("COOKIE_SECURE")
    if secure_raw is not None and secure_raw.strip().lower() in {"0", "false", "no", "off"}:
        problems.append("COOKIE_SECURE выключен: cookie сессии должны передаваться только по HTTPS")

    if not [item for item in source.get("ALLOWED_HOSTS", "").split(",") if item.strip()]:
        problems.append("ALLOWED_HOSTS не задан: укажите домен сайта, например nutrition.example.com")

    if source.get("ENABLE_DOCS", "").strip().lower() in {"1", "true", "yes", "on"}:
        problems.append("ENABLE_DOCS включён: документация API не должна быть открыта на публичном сервере")

    return problems


def validate_settings() -> None:
    """При запуске в production останавливает сервер, если настройки небезопасны. В разработке ничего не делает."""
    if not is_production():
        return
    problems = production_problems()
    if problems:
        raise RuntimeError(
            "Небезопасные настройки для ENVIRONMENT=production:\n- " + "\n- ".join(problems)
        )
