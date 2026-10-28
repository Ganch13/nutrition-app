"""Проверка и очистка загружаемых фотографий (шаг 70).

Что делает sanitize_image:
  1. определяет формат по первым байтам файла (JPEG, PNG или WebP), а не по тому,
     что написал клиент в заголовке или в имени файла;
  2. убирает метаданные: координаты GPS, модель телефона, время съёмки, комментарии.
     Фото с телефона обычно содержит место, где оно снято, — в базе и на диске оно не нужно;
  3. у JPEG сохраняет только поворот (Orientation), иначе портретные снимки лягут набок.

Картинка при этом не перекодируется: пиксели остаются теми же, меняются только служебные блоки.
"""

JPEG = "image/jpeg"
PNG = "image/png"
WEBP = "image/webp"

EXTENSIONS = {JPEG: ".jpg", PNG: ".png", WEBP: ".webp"}

# Блоки PNG с метаданными: EXIF, текстовые комментарии, время последнего изменения
_PNG_DROP = {b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"}
# Блоки WebP с метаданными
_WEBP_DROP = {b"EXIF", b"XMP "}


class InvalidImageError(Exception):
    # Файл не JPEG/PNG/WebP или повреждён
    pass


def detect_image_type(data: bytes) -> str | None:
    """Формат по сигнатуре файла: b"\\xff\\xd8\\xff..." → "image/jpeg"; неизвестный формат → None."""
    if data[:3] == b"\xff\xd8\xff":
        return JPEG
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return PNG
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return WEBP
    return None


def sanitize_image(data: bytes) -> tuple[bytes, str]:
    """Проверяет формат и убирает метаданные. Возвращает (очищенные байты, тип содержимого).

    Пример: JPEG с GPS-координатами в EXIF → (тот же JPEG без EXIF, "image/jpeg").
    Выбрасывает InvalidImageError, если формат неизвестен или структура файла нарушена.
    """
    content_type = detect_image_type(data)
    if content_type is None:
        raise InvalidImageError("Неподдерживаемый формат")
    cleaners = {JPEG: _strip_jpeg, PNG: _strip_png, WEBP: _strip_webp}
    return cleaners[content_type](data), content_type


# ------------------------------------------------------------------ JPEG


def _jpeg_orientation(tiff: bytes) -> int | None:
    """Поворот из EXIF: читает тег Orientation (0x0112). Значения 1–8, иначе None.

    tiff — содержимое EXIF после слов "Exif\\0\\0": заголовок порядка байтов ("II" или "MM"),
    число 42, смещение первой таблицы тегов (IFD0) и сами теги по 12 байт.
    """
    if len(tiff) < 8:
        return None
    order = {b"II": "little", b"MM": "big"}.get(tiff[:2])
    if order is None or int.from_bytes(tiff[2:4], order) != 42:
        return None
    offset = int.from_bytes(tiff[4:8], order)
    if offset + 2 > len(tiff):
        return None
    for index in range(int.from_bytes(tiff[offset : offset + 2], order)):
        entry = offset + 2 + 12 * index
        if entry + 12 > len(tiff):
            return None
        if int.from_bytes(tiff[entry : entry + 2], order) == 0x0112:
            value = int.from_bytes(tiff[entry + 8 : entry + 10], order)
            return value if 1 <= value <= 8 else None
    return None


def _orientation_segment(orientation: int) -> bytes:
    """Минимальный блок APP1/EXIF, в котором есть только поворот. Пример: 6 → блок на 36 байт."""
    tiff = (
        b"MM\x00\x2a\x00\x00\x00\x08"  # порядок байтов, число 42, смещение таблицы = 8
        + b"\x00\x01"  # в таблице один тег
        + b"\x01\x12\x00\x03\x00\x00\x00\x01"  # тег 0x0112, тип SHORT, одно значение
        + orientation.to_bytes(2, "big")
        + b"\x00\x00"  # значение занимает 2 байта из 4, остальное — выравнивание
        + b"\x00\x00\x00\x00"  # следующей таблицы нет
    )
    payload = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload


def _strip_jpeg(data: bytes) -> bytes:
    """Убирает из JPEG блоки APP1 (EXIF, XMP), APP13 (IPTC/Photoshop) и комментарии COM.

    JPEG состоит из блоков: маркер FF xx и длина (включая 2 байта длины). Доходим до маркера
    начала сжатых данных SOS (FF DA) и копируем остаток как есть. Блок профиля цвета (APP2) остаётся.
    """
    kept: list[bytes] = []
    orientation = None
    pos = 2  # после маркера начала файла FF D8
    while True:
        if pos + 2 > len(data) or data[pos] != 0xFF:
            raise InvalidImageError("Повреждённый JPEG")
        marker = data[pos + 1]
        if marker == 0xFF:  # заполняющий байт между блоками
            pos += 1
            continue
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:  # маркеры без длины
            kept.append(data[pos : pos + 2])
            pos += 2
            continue
        if marker == 0xD9:  # конец файла
            kept.append(data[pos : pos + 2])
            break
        if pos + 4 > len(data):
            raise InvalidImageError("Повреждённый JPEG")
        length = int.from_bytes(data[pos + 2 : pos + 4], "big")
        end = pos + 2 + length
        if length < 2 or end > len(data):
            raise InvalidImageError("Повреждённый JPEG")
        if marker == 0xDA:  # начало сжатых данных: дальше только они
            kept.append(data[pos:])
            break
        segment = data[pos:end]
        if marker == 0xE1 and segment[4:10] == b"Exif\x00\x00":
            orientation = _jpeg_orientation(segment[10:])
        if marker not in (0xE1, 0xED, 0xFE):
            kept.append(segment)
        pos = end

    head = [b"\xff\xd8"]
    if orientation is not None and orientation != 1:
        head.append(_orientation_segment(orientation))
    return b"".join(head + kept)


# ------------------------------------------------------------------ PNG


def _strip_png(data: bytes) -> bytes:
    """Убирает из PNG блоки eXIf, tEXt, zTXt, iTXt, tIME и всё, что записано после IEND."""
    if data[12:16] != b"IHDR":
        raise InvalidImageError("Повреждённый PNG")
    out = bytearray(data[:8])
    pos = 8
    while pos + 12 <= len(data):
        length = int.from_bytes(data[pos : pos + 4], "big")
        end = pos + 12 + length  # длина + тип + данные + контрольная сумма
        if end > len(data):
            break
        chunk_type = data[pos + 4 : pos + 8]
        if chunk_type not in _PNG_DROP:
            out += data[pos:end]
        pos = end
        if chunk_type == b"IEND":
            return bytes(out)
    raise InvalidImageError("Повреждённый PNG")


# ------------------------------------------------------------------ WebP


def _strip_webp(data: bytes) -> bytes:
    """Убирает из WebP блоки EXIF и XMP и сбрасывает их флаги в заголовке VP8X."""
    if len(data) < 20:
        raise InvalidImageError("Повреждённый WebP")
    end = min(len(data), 8 + int.from_bytes(data[4:8], "little"))
    chunks: list[bytes] = []
    pos = 12
    while pos + 8 <= end:
        fourcc = data[pos : pos + 4]
        size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        chunk_end = pos + 8 + size + (size % 2)  # данные выравниваются до чётного числа байт
        if chunk_end > len(data):
            raise InvalidImageError("Повреждённый WebP")
        if fourcc not in _WEBP_DROP:
            chunk = bytearray(data[pos:chunk_end])
            if fourcc == b"VP8X" and size >= 1:
                chunk[8] &= ~0x0C  # флаги «есть EXIF» (0x08) и «есть XMP» (0x04)
            chunks.append(bytes(chunk))
        pos = chunk_end
    if not chunks:
        raise InvalidImageError("Повреждённый WebP")
    body = b"WEBP" + b"".join(chunks)
    return b"RIFF" + len(body).to_bytes(4, "little") + body
