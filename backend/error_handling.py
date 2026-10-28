"""Общий помощник: превращает ошибки бизнес-логики в HTTP-ответы.

Каждый модуль (расписание, продукты, планы питания…) описывает словарь
«класс ошибки → (код ответа, текст)» и один раз вызывает register_error_map.
После этого в эндпоинтах не нужны блоки try/except: сервис просто бросает ошибку,
а клиент получает JSON вида {"detail": "..."} с нужным кодом.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def register_error_map(
    app: FastAPI,
    mapping: dict[type[Exception], tuple[int, str]],
) -> None:
    """Подключает обработчики ошибок из словаря mapping к приложению app.

    Пример mapping: {EventMissingError: (404, "Событие не найдено")}
    """
    for exception_class, (status_code, detail) in mapping.items():
        # Значения передаём как параметры по умолчанию: каждый обработчик
        # запоминает свои значения, а не последние из цикла
        async def handler(
            request: Request,
            exc: Exception,
            status_code: int = status_code,
            detail: str = detail,
        ):
            return JSONResponse(status_code=status_code, content={"detail": detail})

        app.add_exception_handler(exception_class, handler)
