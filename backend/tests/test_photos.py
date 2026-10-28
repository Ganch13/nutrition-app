"""Тесты шага 70: фото прогресса."""

from datetime import date, timedelta

import pytest
from sqlalchemy.exc import SQLAlchemyError

import photo_services
from photo_utils import (
    InvalidImageError,
    _jpeg_orientation,
    _orientation_segment,
    detect_image_type,
    sanitize_image,
)
from tests.helpers import register_and_login
from tests.photo_samples import JPEG_PLAIN, JPEG_WITH_EXIF, PNG_WITH_TEXT, WEBP_WITH_EXIF

SECRETS = (b"SecretPhoneMaker", b"SecretPhoneModel", b"SecretGpsComment")
TODAY = date.today().isoformat()


def assert_clean(data: bytes):
    for secret in SECRETS:
        assert secret not in data, secret


# ---------------------------------------------------------------- очистка файлов (без сервера)


def test_detect_image_type_by_signature():
    assert detect_image_type(JPEG_PLAIN) == "image/jpeg"
    assert detect_image_type(PNG_WITH_TEXT) == "image/png"
    assert detect_image_type(WEBP_WITH_EXIF) == "image/webp"
    assert detect_image_type(b"") is None
    assert detect_image_type(b"GIF89a....") is None
    assert detect_image_type(b"<html><script>alert(1)</script>") is None
    assert detect_image_type(b"RIFF\x00\x00\x00\x00WAVE") is None  # RIFF, но не WebP


def test_jpeg_metadata_is_removed_but_rotation_and_pixels_stay():
    assert any(secret in JPEG_WITH_EXIF for secret in SECRETS)  # проверяем сам образец

    clean, content_type = sanitize_image(JPEG_WITH_EXIF)

    assert content_type == "image/jpeg"
    assert_clean(clean)
    assert len(clean) < len(JPEG_WITH_EXIF)
    assert clean[:2] == b"\xff\xd8" and clean[-2:] == b"\xff\xd9"
    # Поворот из EXIF сохранён: иначе портретные снимки лягут набок
    start = clean.index(b"Exif\x00\x00") + 6
    assert _jpeg_orientation(clean[start:]) == 6
    # Само изображение (от начала сжатых данных) не тронуто
    assert clean.endswith(JPEG_WITH_EXIF[JPEG_WITH_EXIF.index(b"\xff\xda") :])


def test_jpeg_without_metadata_is_not_changed():
    assert sanitize_image(JPEG_PLAIN) == (JPEG_PLAIN, "image/jpeg")


def test_orientation_segment_round_trip():
    for orientation in range(2, 9):
        segment = _orientation_segment(orientation)
        assert segment[:2] == b"\xff\xe1" and int.from_bytes(segment[2:4], "big") == len(segment) - 2
        assert _jpeg_orientation(segment[10:]) == orientation
    assert _jpeg_orientation(b"") is None
    assert _jpeg_orientation(b"XX\x00\x2a\x00\x00\x00\x08") is None


def test_png_text_and_exif_chunks_are_removed():
    assert any(secret in PNG_WITH_TEXT for secret in SECRETS)

    clean, content_type = sanitize_image(PNG_WITH_TEXT + b"TRAILING-GARBAGE")

    assert content_type == "image/png"
    assert_clean(clean)
    assert b"eXIf" not in clean and b"tEXt" not in clean
    assert b"IDAT" in clean and clean.endswith(b"IEND\xaeB`\x82")  # данные картинки и конец файла на месте


def test_webp_exif_is_removed_and_header_stays_valid():
    assert b"EXIF" in WEBP_WITH_EXIF

    clean, content_type = sanitize_image(WEBP_WITH_EXIF)

    assert content_type == "image/webp"
    assert_clean(clean)
    assert b"EXIF" not in clean
    assert clean[:4] == b"RIFF" and clean[8:12] == b"WEBP"
    assert int.from_bytes(clean[4:8], "little") == len(clean) - 8
    assert clean[12:16] == b"VP8X" and clean[20] & 0x0C == 0  # флаги EXIF и XMP сброшены


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not an image at all",
        JPEG_PLAIN[:10],  # обрезанный JPEG
        JPEG_PLAIN[:2] + b"\xff\xe1\xff\xff" + JPEG_PLAIN[6:],  # блок длиннее файла
        PNG_WITH_TEXT[:20],  # обрезанный PNG
        PNG_WITH_TEXT[:12] + b"XXXX" + PNG_WITH_TEXT[16:],  # первый блок не IHDR
        PNG_WITH_TEXT[:-12],  # нет блока IEND
        WEBP_WITH_EXIF[:15],
    ],
    ids=["empty", "text", "jpeg-truncated", "jpeg-bad-length", "png-truncated", "png-no-ihdr", "png-no-iend", "webp-truncated"],
)
def test_broken_files_are_rejected(data):
    with pytest.raises(InvalidImageError):
        sanitize_image(data)


# ---------------------------------------------------------------- загрузка и выдача


def upload(client, user, data=JPEG_WITH_EXIF, content_type="image/jpeg", **params):
    params = {"taken_on": TODAY, **params}
    headers = {**user["headers"], "Content-Type": content_type}
    return client.post(f"/users/{user['id']}/progress-photos", params=params, content=data, headers=headers)


def photos_url(user, suffix=""):
    return f"/users/{user['id']}/progress-photos{suffix}"


def stored_files(upload_dir):
    return sorted(path for path in upload_dir.rglob("*") if path.is_file()) if upload_dir.exists() else []


def test_upload_requires_login_and_own_account(client):
    owner = register_and_login(client, "a@example.com")
    stranger = register_and_login(client, "b@example.com")

    anonymous = client.post(photos_url(owner), params={"taken_on": TODAY}, content=JPEG_PLAIN, headers={"Content-Type": "image/jpeg"})
    assert anonymous.status_code == 401
    assert upload(client, stranger, JPEG_PLAIN).status_code == 201  # у себя можно
    foreign = client.post(
        photos_url(owner), params={"taken_on": TODAY}, content=JPEG_PLAIN,
        headers={**stranger["headers"], "Content-Type": "image/jpeg"},
    )
    assert foreign.status_code == 403


def test_upload_saves_clean_file_and_returns_metadata(client, upload_dir):
    user = register_and_login(client, "a@example.com")

    response = upload(client, user, angle="side", note="  Утром, натощак  ")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["taken_on"] == TODAY and body["angle"] == "side" and body["note"] == "Утром, натощак"
    assert body["content_type"] == "image/jpeg" and body["url"] == photos_url(user, f"/{body['id']}/file")
    assert "storage_name" not in body  # внутреннее имя файла наружу не отдаётся

    # Файл лежит в папке пользователя под случайным именем, а не под присланным
    (path,) = stored_files(upload_dir)
    assert path.parent == upload_dir / "progress" / str(user["id"])
    assert path.suffix == ".jpg" and len(path.stem) == 32 and int(path.stem, 16) >= 0
    assert_clean(path.read_bytes())
    assert body["size_bytes"] == path.stat().st_size < len(JPEG_WITH_EXIF)


def test_file_endpoint_returns_image_with_safe_headers(client):
    user = register_and_login(client, "a@example.com")
    photo = upload(client, user).json()

    response = client.get(photo["url"], headers=user["headers"])

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"].startswith("private")
    assert response.content == sanitize_image(JPEG_WITH_EXIF)[0]
    assert client.get(photo["url"]).status_code == 401


@pytest.mark.parametrize(
    "data, content_type, extension",
    [(PNG_WITH_TEXT, "image/png", ".png"), (WEBP_WITH_EXIF, "image/webp", ".webp")],
    ids=["png", "webp"],
)
def test_png_and_webp_are_supported(client, upload_dir, data, content_type, extension):
    user = register_and_login(client, "a@example.com")

    response = upload(client, user, data, content_type)

    assert response.status_code == 201, response.text
    assert response.json()["content_type"] == content_type
    (path,) = stored_files(upload_dir)
    assert path.suffix == extension
    assert_clean(path.read_bytes())
    assert client.get(response.json()["url"], headers=user["headers"]).headers["content-type"] == content_type


def test_content_type_with_parameters_is_accepted(client):
    user = register_and_login(client, "a@example.com")
    assert upload(client, user, content_type="IMAGE/JPEG; charset=binary").status_code == 201


@pytest.mark.parametrize(
    "data, content_type",
    [
        (PNG_WITH_TEXT, "image/jpeg"),  # заголовок врёт
        (JPEG_PLAIN, "text/plain"),  # неподдерживаемый тип
        (JPEG_PLAIN, "application/octet-stream"),
        (b"<script>alert(1)</script>", "image/jpeg"),  # не картинка
        (b"GIF89a" + b"\x00" * 50, "image/gif"),
        (JPEG_PLAIN[:10], "image/jpeg"),  # обрезанный файл
    ],
    ids=["header-lies", "text-plain", "octet-stream", "script", "gif", "truncated"],
)
def test_wrong_files_are_rejected_and_nothing_is_saved(client, upload_dir, data, content_type):
    user = register_and_login(client, "a@example.com")

    response = upload(client, user, data, content_type)

    assert response.status_code == 415, response.text
    assert "JPEG, PNG и WebP" in response.json()["detail"]
    assert stored_files(upload_dir) == []
    assert client.get(photos_url(user), headers=user["headers"]).json() == []


def test_empty_body_is_rejected(client):
    user = register_and_login(client, "a@example.com")
    response = upload(client, user, b"")
    assert response.status_code == 400 and response.json()["detail"] == "Файл пустой"


def test_size_limit_is_enforced_by_header_and_while_reading(client, upload_dir, monkeypatch):
    monkeypatch.setenv("MAX_PHOTO_MB", "1")
    user = register_and_login(client, "a@example.com")
    big = JPEG_PLAIN + b"\x00" * (1024 * 1024)  # чуть больше мегабайта

    # Размер известен заранее (Content-Length)
    assert upload(client, user, big).status_code == 413

    # Размера в заголовке нет (передача частями): лимит срабатывает по мере чтения
    def chunks():
        for _ in range(3):
            yield big[: 512 * 1024]

    streamed = client.post(
        photos_url(user), params={"taken_on": TODAY}, content=chunks(),
        headers={**user["headers"], "Content-Type": "image/jpeg"},
    )
    assert streamed.status_code == 413
    assert stored_files(upload_dir) == []

    # Файл ровно в пределах лимита проходит
    assert upload(client, user, JPEG_PLAIN + b"\x00" * (1024 * 1024 - len(JPEG_PLAIN) - 10)).status_code == 201


def test_upload_validates_query_parameters(client):
    user = register_and_login(client, "a@example.com")
    tomorrow = (date.today() + timedelta(days=2)).isoformat()

    assert upload(client, user, taken_on=tomorrow).status_code == 422
    assert upload(client, user, angle="top").status_code == 422
    assert upload(client, user, note="x" * 301).status_code == 422
    missing = client.post(photos_url(user), content=JPEG_PLAIN, headers={**user["headers"], "Content-Type": "image/jpeg"})
    assert missing.status_code == 422

    blank_note = upload(client, user, note="   ").json()
    assert blank_note["note"] is None


def test_photo_limit_per_user(client, monkeypatch):
    monkeypatch.setattr(photo_services, "MAX_PHOTOS_PER_USER", 2)
    user = register_and_login(client, "a@example.com")
    other = register_and_login(client, "b@example.com")

    assert upload(client, user).status_code == 201
    assert upload(client, user).status_code == 201
    third = upload(client, user)
    assert third.status_code == 409 and "предел" in third.json()["detail"]
    assert upload(client, other).status_code == 201  # лимит у каждого свой


def test_file_is_removed_when_database_write_fails(client, upload_dir, monkeypatch):
    user = register_and_login(client, "a@example.com")

    def broken_commit(self):
        raise SQLAlchemyError("база недоступна")

    monkeypatch.setattr("sqlalchemy.orm.Session.commit", broken_commit)
    with pytest.raises(SQLAlchemyError):
        upload(client, user)
    monkeypatch.undo()

    assert stored_files(upload_dir) == []  # осиротевший файл не остался


def test_no_temporary_files_are_left_after_upload(client, upload_dir):
    user = register_and_login(client, "a@example.com")
    upload(client, user)
    assert [path.suffix for path in stored_files(upload_dir)] == [".jpg"]


def test_two_uploads_get_different_file_names(client, upload_dir):
    user = register_and_login(client, "a@example.com")
    upload(client, user, JPEG_PLAIN)
    upload(client, user, JPEG_PLAIN)
    assert len({path.name for path in stored_files(upload_dir)}) == 2


def test_swagger_shows_file_picker(client):
    schema = client.get("/openapi.json").json()
    body = schema["paths"]["/users/{user_id}/progress-photos"]["post"]["requestBody"]["content"]
    assert body["image/jpeg"]["schema"] == {"type": "string", "format": "binary"}


# ---------------------------------------------------------------- список, изменение, удаление


def test_list_filters_and_order(client):
    user = register_and_login(client, "a@example.com")
    other = register_and_login(client, "b@example.com")
    first = upload(client, user, taken_on="2026-09-01", angle="front").json()
    second = upload(client, user, taken_on="2026-10-01", angle="side").json()
    third = upload(client, user, taken_on="2026-10-01", angle="front").json()
    upload(client, other, taken_on="2026-10-02")

    def listing(**params):
        response = client.get(photos_url(user), params=params, headers=user["headers"])
        assert response.status_code == 200, response.text
        return [item["id"] for item in response.json()]

    # Новые сверху; при одинаковой дате — позже загруженное выше
    assert listing() == [third["id"], second["id"], first["id"]]
    assert listing(angle="front") == [third["id"], first["id"]]
    assert listing(date_from="2026-10-01") == [third["id"], second["id"]]
    assert listing(date_to="2026-09-30") == [first["id"]]
    assert listing(limit=1, offset=1) == [second["id"]]
    assert client.get(photos_url(user), params={"limit": 0}, headers=user["headers"]).status_code == 422
    assert client.get(photos_url(user), params={"angle": "top"}, headers=user["headers"]).status_code == 422


def test_update_photo_fields(client):
    user = register_and_login(client, "a@example.com")
    photo = upload(client, user, taken_on="2026-10-20", note="До").json()
    url = photos_url(user, f"/{photo['id']}")

    changed = client.patch(url, json={"taken_on": "2026-10-19", "angle": "back"}, headers=user["headers"])
    assert changed.status_code == 200, changed.text
    assert (changed.json()["taken_on"], changed.json()["angle"], changed.json()["note"]) == ("2026-10-19", "back", "До")

    # Подпись очищается явным null; пустое тело ничего не меняет
    assert client.patch(url, json={"note": None}, headers=user["headers"]).json()["note"] is None
    unchanged = client.patch(url, json={}, headers=user["headers"]).json()
    assert (unchanged["taken_on"], unchanged["angle"]) == ("2026-10-19", "back")

    future = (date.today() + timedelta(days=3)).isoformat()
    assert client.patch(url, json={"taken_on": future}, headers=user["headers"]).status_code == 422
    assert client.patch(url, json={"angle": "top"}, headers=user["headers"]).status_code == 422
    assert client.patch(photos_url(user, "/999"), json={}, headers=user["headers"]).status_code == 404


def test_delete_removes_record_and_file(client, upload_dir):
    user = register_and_login(client, "a@example.com")
    photo = upload(client, user).json()
    assert len(stored_files(upload_dir)) == 1

    assert client.delete(photos_url(user, f"/{photo['id']}"), headers=user["headers"]).status_code == 204

    assert stored_files(upload_dir) == []
    assert client.get(photos_url(user, f"/{photo['id']}"), headers=user["headers"]).status_code == 404
    assert client.get(photo["url"], headers=user["headers"]).status_code == 404
    assert client.delete(photos_url(user, f"/{photo['id']}"), headers=user["headers"]).status_code == 404


def test_missing_file_gives_clear_error_but_metadata_remains(client, upload_dir):
    user = register_and_login(client, "a@example.com")
    photo = upload(client, user).json()
    for path in stored_files(upload_dir):
        path.unlink()

    response = client.get(photo["url"], headers=user["headers"])

    assert response.status_code == 404 and "не найден на сервере" in response.json()["detail"]
    assert client.get(photos_url(user, f"/{photo['id']}"), headers=user["headers"]).status_code == 200
    # Запись всё равно можно удалить
    assert client.delete(photos_url(user, f"/{photo['id']}"), headers=user["headers"]).status_code == 204


def test_photos_are_private(client, upload_dir):
    owner = register_and_login(client, "a@example.com")
    stranger = register_and_login(client, "b@example.com")
    photo = upload(client, owner).json()
    photo_id = photo["id"]

    # Чужая учётная запись в адресе: 403
    for method, suffix in (("get", ""), ("get", f"/{photo_id}"), ("get", f"/{photo_id}/file"), ("delete", f"/{photo_id}")):
        response = getattr(client, method)(photos_url(owner, suffix), headers=stranger["headers"])
        assert response.status_code == 403, (method, suffix)
    assert client.patch(photos_url(owner, f"/{photo_id}"), json={"note": "x"}, headers=stranger["headers"]).status_code == 403

    # Свой адрес, но чужой номер фото: 404, как будто фото не существует
    for method, suffix in (("get", f"/{photo_id}"), ("get", f"/{photo_id}/file"), ("delete", f"/{photo_id}")):
        response = getattr(client, method)(photos_url(stranger, suffix), headers=stranger["headers"])
        assert response.status_code == 404, (method, suffix)
    assert client.patch(photos_url(stranger, f"/{photo_id}"), json={"note": "x"}, headers=stranger["headers"]).status_code == 404

    # Ничего не пострадало
    assert client.get(photos_url(stranger), headers=stranger["headers"]).json() == []
    assert len(stored_files(upload_dir)) == 1
    assert client.get(photo["url"], headers=owner["headers"]).status_code == 200
