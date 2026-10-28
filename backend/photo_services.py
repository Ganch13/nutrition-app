"""Фото прогресса: хранение файлов на диске и данных о них в базе (шаг 70).

Как это устроено:
  * файл сохраняется в <UPLOAD_DIR>/progress/<id пользователя>/<случайное имя>;
  * имя файла создаёт сервер (uuid), из присланного пользователем имени ничего не берётся,
    поэтому подставить путь вроде "../../etc/passwd" невозможно;
  * перед сохранением формат проверяется по содержимому, а метаданные (GPS и др.) удаляются
    (см. photo_utils.sanitize_image);
  * фото видит только владелец: чужой id фото отвечает так же, как несуществующий.
"""

import logging
import os
import uuid
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from config import get_upload_dir
from models import ProgressPhoto
from photo_utils import EXTENSIONS, InvalidImageError, sanitize_image
from schedule_services import _user_timezone
from schemas import ProgressPhotoResponse, ProgressPhotoUpdate

logger = logging.getLogger(__name__)

# Сколько фото может хранить один пользователь (защита диска сервера от переполнения)
MAX_PHOTOS_PER_USER = 300


class PhotoNotFoundError(Exception):
    # Фото нет или оно принадлежит другому пользователю
    pass


class PhotoFileMissingError(Exception):
    # Запись в базе есть, а файла на диске нет (например, том с файлами не подключён)
    pass


class PhotoTooLargeError(Exception):
    # Размер превышает MAX_PHOTO_MB
    pass


class UnsupportedPhotoError(Exception):
    # Не JPEG/PNG/WebP, повреждённый файл или тип в заголовке не совпал с содержимым
    pass


class EmptyPhotoError(Exception):
    # Тело запроса пустое
    pass


class PhotoLimitReachedError(Exception):
    # У пользователя уже MAX_PHOTOS_PER_USER фото
    pass


class PhotoDateInFutureError(Exception):
    # Дата съёмки позже сегодняшней
    pass


def photo_path(photo: ProgressPhoto) -> Path:
    """Путь к файлу фото. Пример: uploads/progress/1/3f2a9c71d0e84b5c9a1b2c3d4e5f6a7b.jpg."""
    return Path(get_upload_dir()) / "progress" / str(photo.user_id) / photo.storage_name


def to_response(photo: ProgressPhoto) -> ProgressPhotoResponse:
    """Данные о фото для ответа; url — адрес, по которому (с токеном) отдаётся сам файл."""
    return ProgressPhotoResponse(
        id=photo.id,
        taken_on=photo.taken_on,
        angle=photo.angle,  # type: ignore[arg-type]
        note=photo.note,
        content_type=photo.content_type,
        size_bytes=photo.size_bytes,
        created_at=photo.created_at,
        url=f"/users/{photo.user_id}/progress-photos/{photo.id}/file",
    )


def _check_taken_on(db: Session, user_id: int, taken_on: date) -> None:
    """Дата съёмки не может быть в будущем (сегодня считается по часовому поясу пользователя)."""
    today = datetime.now(_user_timezone(db, user_id)).date()
    if taken_on > today:
        raise PhotoDateInFutureError


def save_photo(
    db: Session,
    user_id: int,
    data: bytes,
    declared_type: str,
    taken_on: date,
    angle: str,
    note: str | None,
) -> ProgressPhoto:
    """Проверяет и сохраняет фото. declared_type — заголовок Content-Type запроса.

    Пример: data — байты JPEG, declared_type="image/jpeg", taken_on=date(2026, 10, 27), angle="front"
    → файл на диске без метаданных и строка в progress_photos.
    """
    if not data:
        raise EmptyPhotoError
    try:
        clean, content_type = sanitize_image(data)
    except InvalidImageError as error:
        raise UnsupportedPhotoError from error
    if declared_type != content_type:
        raise UnsupportedPhotoError  # заголовок говорит одно, а в файле другое

    _check_taken_on(db, user_id, taken_on)
    count = db.scalar(select(func.count()).select_from(ProgressPhoto).where(ProgressPhoto.user_id == user_id))
    if count is not None and count >= MAX_PHOTOS_PER_USER:
        raise PhotoLimitReachedError

    storage_name = f"{uuid.uuid4().hex}{EXTENSIONS[content_type]}"
    photo = ProgressPhoto(
        user_id=user_id,
        taken_on=taken_on,
        angle=angle,
        note=(note.strip() or None) if note else None,
        storage_name=storage_name,
        content_type=content_type,
        size_bytes=len(clean),
    )
    path = photo_path(photo)
    # Сначала файл во временное имя, потом переименование: недописанный файл не появится под настоящим именем
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".part")
    temp.write_bytes(clean)
    os.replace(temp, path)

    try:
        db.add(photo)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        path.unlink(missing_ok=True)  # записи нет — файл никому не нужен
        raise
    db.refresh(photo)
    return photo


def get_photo(db: Session, user_id: int, photo_id: int) -> ProgressPhoto:
    """Фото пользователя по id; чужое или несуществующее — PhotoNotFoundError."""
    photo = db.scalar(select(ProgressPhoto).where(ProgressPhoto.id == photo_id, ProgressPhoto.user_id == user_id))
    if photo is None:
        raise PhotoNotFoundError
    return photo


def list_photos(
    db: Session,
    user_id: int,
    angle: str | None,
    date_from: date | None,
    date_to: date | None,
    limit: int,
    offset: int,
) -> list[ProgressPhoto]:
    """Фото пользователя, новые сверху. Пример: angle="front", date_from=2026-10-01 → фронтальные за октябрь."""
    query = select(ProgressPhoto).where(ProgressPhoto.user_id == user_id)
    if angle is not None:
        query = query.where(ProgressPhoto.angle == angle)
    if date_from is not None:
        query = query.where(ProgressPhoto.taken_on >= date_from)
    if date_to is not None:
        query = query.where(ProgressPhoto.taken_on <= date_to)
    query = query.order_by(ProgressPhoto.taken_on.desc(), ProgressPhoto.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(query))


def update_photo(db: Session, user_id: int, photo_id: int, data: ProgressPhotoUpdate) -> ProgressPhoto:
    """Меняет дату, ракурс или подпись. Поля, которых нет в запросе, остаются прежними."""
    photo = get_photo(db, user_id, photo_id)
    if "taken_on" in data.model_fields_set and data.taken_on is not None:
        _check_taken_on(db, user_id, data.taken_on)
        photo.taken_on = data.taken_on
    if "angle" in data.model_fields_set and data.angle is not None:
        photo.angle = data.angle
    if "note" in data.model_fields_set:
        photo.note = data.note
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(photo)
    return photo


def delete_photo(db: Session, user_id: int, photo_id: int) -> None:
    """Удаляет запись и файл. Сначала база: если файл не удалился, пользователь этого не увидит."""
    photo = get_photo(db, user_id, photo_id)
    path = photo_path(photo)
    try:
        db.delete(photo)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Не удалось удалить файл фото %s", path, exc_info=True)
