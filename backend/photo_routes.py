"""Эндпоинты фото прогресса (шаг 70).

Загрузка — «сырым» телом запроса: тело — это сам файл, а Content-Type — его тип
(image/jpeg, image/png или image/webp). Так не нужна библиотека разбора форм,
а размер можно ограничить прямо во время чтения.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from access import require_same_user
from config import get_max_photo_bytes
from database import get_db
from error_handling import register_error_map
from photo_services import (
    EmptyPhotoError,
    PhotoDateInFutureError,
    PhotoFileMissingError,
    PhotoLimitReachedError,
    PhotoNotFoundError,
    PhotoTooLargeError,
    UnsupportedPhotoError,
    delete_photo,
    get_photo,
    list_photos,
    photo_path,
    save_photo,
    to_response,
    update_photo,
)
from schemas import PhotoAngle, ProgressPhotoResponse, ProgressPhotoUpdate

router = APIRouter(
    prefix="/users/{user_id}/progress-photos",
    tags=["progress-photos"],
    # Все пути ниже доступны только владельцу данных
    dependencies=[Depends(require_same_user)],
)

ERROR_RESPONSES = {
    PhotoNotFoundError: (404, "Фото не найдено"),
    PhotoFileMissingError: (404, "Файл фото не найден на сервере"),
    PhotoTooLargeError: (413, "Фото слишком большое. Уменьшите размер файла (по умолчанию допустимо до 8 МБ)"),
    UnsupportedPhotoError: (415, "Поддерживаются только фото JPEG, PNG и WebP. Проверьте файл и заголовок Content-Type"),
    EmptyPhotoError: (400, "Файл пустой"),
    PhotoLimitReachedError: (409, "Достигнут предел числа фото. Удалите ненужные и повторите"),
    PhotoDateInFutureError: (422, "Дата съёмки не может быть в будущем"),
}


def register_error_handlers(app: FastAPI) -> None:
    register_error_map(app, ERROR_RESPONSES)


# Чтобы в Swagger UI появилось поле выбора файла, описываем тело запроса вручную
_UPLOAD_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            content_type: {"schema": {"type": "string", "format": "binary"}}
            for content_type in ("image/jpeg", "image/png", "image/webp")
        },
    }
}


@router.post("", response_model=ProgressPhotoResponse, status_code=201, openapi_extra=_UPLOAD_BODY)
async def upload_photo_endpoint(
    user_id: int,
    request: Request,
    taken_on: date,
    angle: PhotoAngle = "front",
    note: Annotated[str | None, Query(max_length=300)] = None,
    db: Session = Depends(get_db),
):
    """Загружает фото. Тело запроса — файл, заголовок Content-Type — его тип.

    Запрос: POST /users/1/progress-photos?taken_on=2026-10-27&angle=front&note=Утром
            Content-Type: image/jpeg  (тело — байты файла)
    Ответ 201: {"id": 3, "taken_on": "2026-10-27", "angle": "front", "note": "Утром", ...,
                "url": "/users/1/progress-photos/3/file"}
    Из файла удаляются метаданные (GPS и др.). Ошибки: 413 — слишком большой, 415 — не JPEG/PNG/WebP.
    """
    limit = get_max_photo_bytes()
    declared_length = request.headers.get("content-length", "")
    if declared_length.isdigit() and int(declared_length) > limit:
        raise PhotoTooLargeError  # не читаем тело, если заранее известно, что оно велико

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise PhotoTooLargeError
        chunks.append(chunk)

    declared_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    # Проверка и запись файла блокируют поток, поэтому выполняем их вне основного цикла
    photo = await run_in_threadpool(save_photo, db, user_id, b"".join(chunks), declared_type, taken_on, angle, note)
    return to_response(photo)


@router.get("", response_model=list[ProgressPhotoResponse])
def list_photos_endpoint(
    user_id: int,
    angle: PhotoAngle | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
):
    """Список фото, новые сверху. Запрос: GET /users/1/progress-photos?angle=front&date_from=2026-10-01."""
    return [to_response(photo) for photo in list_photos(db, user_id, angle, date_from, date_to, limit, offset)]


@router.get("/{photo_id}", response_model=ProgressPhotoResponse)
def get_photo_endpoint(user_id: int, photo_id: int, db: Session = Depends(get_db)):
    """Данные одного фото (без самого файла)."""
    return to_response(get_photo(db, user_id, photo_id))


@router.get("/{photo_id}/file")
def get_photo_file_endpoint(user_id: int, photo_id: int, db: Session = Depends(get_db)):
    """Сам файл. Нужен токен, поэтому в <img src> напрямую не вставляется — интерфейс загружает его запросом."""
    photo = get_photo(db, user_id, photo_id)
    path = photo_path(photo)
    if not path.is_file():
        raise PhotoFileMissingError
    return FileResponse(
        path,
        media_type=photo.content_type,
        headers={
            # Только в браузере владельца, не в общих кэшах
            "Cache-Control": "private, max-age=86400",
            # Браузер не должен «угадывать» другой тип по содержимому
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="photo-{photo.id}"',
        },
    )


@router.patch("/{photo_id}", response_model=ProgressPhotoResponse)
def update_photo_endpoint(user_id: int, photo_id: int, data: ProgressPhotoUpdate, db: Session = Depends(get_db)):
    """Меняет дату, ракурс или подпись. Тело: {"taken_on": "2026-10-20", "angle": "side", "note": null}."""
    return to_response(update_photo(db, user_id, photo_id, data))


@router.delete("/{photo_id}", status_code=204)
def delete_photo_endpoint(user_id: int, photo_id: int, db: Session = Depends(get_db)):
    """Удаляет фото вместе с файлом."""
    delete_photo(db, user_id, photo_id)
    return Response(status_code=204)
