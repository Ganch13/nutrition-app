"""
Генератор фирменных картинок «Лад»: значки приложения, favicon и заставки для iPhone.

Запускать вручную не нужно: готовые файлы уже лежат в проекте. Скрипт оставлен, чтобы цвета и форму значка
можно было поменять в одном месте и пересобрать картинки.

Что нужно: Python 3, пакеты fonttools и playwright (с установленным Chromium), Pillow.
Запуск из папки frontend:   python3 design/make_brand_assets.py

Что создаёт:
  app/icon.svg              значок вкладки браузера (векторный)
  app/favicon.ico           запасной значок вкладки (16, 32, 48 px)
  app/apple-icon.png        значок для главного экрана iPhone (180 px, без прозрачности)
  public/icons/*.png        значки PWA для Android и Chrome (192, 512, maskable 512)
  public/brand/*.svg        исходники: значок и надпись «Лад»
  public/splash/*.png       заставки запуска для iPhone разных размеров
  lib/brand-art.ts          контур надписи «Лад» и значка для экрана загрузки внутри приложения
  lib/splash.ts             список заставок с условиями (media), для какого iPhone какая картинка
"""

import json
import pathlib
import tempfile

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ---- Цвета (те же, что в app/globals.css) ----
TILE_TOP = "#3C48B5"
TILE_BOTTOM = "#232A74"
SAFFRON = "#F2A22E"
APP_BG = "#F4F5FB"
INK = "#1A1E3A"
MUTED = "#5C6382"

# Буква «Л» нарисована одной линией в системе координат 512x512
LETTER_PATH = "M142 372 C186 372 206 330 220 264 C234 198 244 148 300 148 C346 148 366 164 366 196 V372"
LETTER_STROKE = 52
DOT = (296, 312, 28)  # x, y, радиус шафрановой точки


def tile_svg(size: int = 512, rounded: bool = True, glyph_scale: float = 1.0) -> str:
    """SVG значка. rounded=False даёт квадрат во всю площадь (для maskable и iOS).
    glyph_scale < 1 уменьшает букву, чтобы она не обрезалась маской Android."""
    radius = 116 if rounded else 0
    shift = 256 * (1 - glyph_scale)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="{size}" height="{size}">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{TILE_TOP}"/>
      <stop offset="1" stop-color="{TILE_BOTTOM}"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="{radius}" fill="url(#g)"/>
  <g transform="translate({shift} {shift}) scale({glyph_scale})">
    <path d="{LETTER_PATH}" fill="none" stroke="#fff" stroke-width="{LETTER_STROKE}" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="{DOT[0]}" cy="{DOT[1]}" r="{DOT[2]}" fill="{SAFFRON}"/>
  </g>
</svg>
"""


def wordmark_path() -> tuple[str, tuple[int, int, int, int]]:
    """Контур надписи «Лад» шрифтом Lora SemiBold: так заставка не зависит от загрузки шрифтов."""
    font = TTFont("/usr/share/fonts/truetype/google-fonts/Lora-Variable.ttf")
    font = instancer.instantiateVariableFont(font, {"wght": 600})
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    x = 0
    parts = []
    for char in "Лад":
        glyph = glyphs[cmap[ord(char)]]
        pen = SVGPathPen(glyphs, ntos=lambda v: str(round(v)))
        glyph.draw(TransformPen(pen, (1, 0, 0, -1, x, 0)))  # переворачиваем ось Y: в SVG она смотрит вниз
        parts.append(pen.getCommands())
        x += glyph.width
    # Рамка надписи: от верха заглавной буквы до низа «д»
    return " ".join(parts), (10, -710, 1895, 900)


def splash_svg(width: int, height: int, word_d: str, box: tuple[int, int, int, int]) -> str:
    """Заставка запуска: светлый фон, значок, надпись «Лад» и подпись."""
    tile = round(width * 0.30)
    word_h = round(width * 0.085)  # высота надписи
    scale = word_h / box[3]
    word_w = box[2] * scale
    cx = width / 2
    top = height * 0.5 - (tile + word_h * 2.2) / 2
    tile_inner = tile_svg(tile).replace('<svg ', '<svg x="%s" y="%s" ' % (cx - tile / 2, top), 1)
    word_y = top + tile + word_h * 0.75
    tag_size = round(width * 0.036)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="{width}" height="{height}" fill="{APP_BG}"/>
  {tile_inner}
  <g transform="translate({cx - word_w / 2 - box[0] * scale} {word_y - box[1] * scale}) scale({scale})">
    <path d="{word_d}" fill="{INK}"/>
  </g>
  <text x="{cx}" y="{word_y + word_h * 1.35 + tag_size}" text-anchor="middle"
        font-family="Inter, Helvetica, Arial, sans-serif" font-size="{tag_size}" fill="{MUTED}">Питание, тренировки и деньги семьи</text>
</svg>
"""


# Размеры экранов iPhone: ширина и высота в точках, плотность пикселей
IPHONES = [
    (440, 956, 3),  # 16 Pro Max, 17 Pro Max
    (402, 874, 3),  # 16 Pro, 17, 17 Pro
    (430, 932, 3),  # 14 Pro Max, 15 Plus, 15 Pro Max, 16 Plus
    (393, 852, 3),  # 14 Pro, 15, 15 Pro, 16
    (428, 926, 3),  # 12 Pro Max, 13 Pro Max, 14 Plus
    (390, 844, 3),  # 12, 12 Pro, 13, 13 Pro, 14
    (375, 812, 3),  # X, XS, 11 Pro, 12 mini, 13 mini
    (414, 896, 3),  # XS Max, 11 Pro Max
    (414, 896, 2),  # XR, 11
    (414, 736, 3),  # 6 Plus, 7 Plus, 8 Plus
    (375, 667, 2),  # 6, 7, 8, SE 2 и 3
    (320, 568, 2),  # 5, 5s, SE 1
    (420, 912, 3),  # iPhone Air
]


def main() -> None:
    word_d, box = wordmark_path()
    for folder in ("public/icons", "public/brand", "public/splash"):
        (ROOT / folder).mkdir(parents=True, exist_ok=True)

    (ROOT / "app/icon.svg").write_text(tile_svg(512), encoding="utf-8")
    (ROOT / "public/brand/mark.svg").write_text(tile_svg(512), encoding="utf-8")
    (ROOT / "public/brand/wordmark.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{box[0]} {box[1]} {box[2]} {box[3]}"><path d="{word_d}" fill="{INK}"/></svg>\n',
        encoding="utf-8",
    )

    # Данные для компонента экрана загрузки внутри приложения
    art = (
        "// Файл создан скриптом design/make_brand_assets.py. Вручную не правьте: поменяйте скрипт и запустите его снова.\n"
        f"export const WORDMARK_PATH = {json.dumps(word_d)};\n"
        f"export const WORDMARK_BOX = {json.dumps(list(box))} as const;\n"
        f"export const LETTER_PATH = {json.dumps(LETTER_PATH)};\n"
        f"export const LETTER_STROKE = {LETTER_STROKE};\n"
        f"export const DOT = {json.dumps(list(DOT))} as const;\n"
    )
    (ROOT / "lib/brand-art.ts").write_text(art, encoding="utf-8")

    # Список заставок для app/layout.tsx: iPhone выбирает картинку по размеру своего экрана
    entries = []
    for width, height, ratio in IPHONES:
        media = (
            f"(device-width: {width}px) and (device-height: {height}px) "
            f"and (-webkit-device-pixel-ratio: {ratio}) and (orientation: portrait)"
        )
        entries.append({"url": f"/splash/iphone-{width * ratio}x{height * ratio}.png", "media": media})
    (ROOT / "lib/splash.ts").write_text(
        "// Файл создан скриптом design/make_brand_assets.py. Вручную не правьте.\n"
        "// Заставки запуска для iPhone: браузер выбирает ту, чьё условие (media) совпало с экраном телефона.\n"
        f"export const IPHONE_SPLASH: {{ url: string; media: string }}[] = {json.dumps(entries, indent=2, ensure_ascii=False)};\n",
        encoding="utf-8",
    )

    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        browser = p.chromium.launch()

        def render(svg: str, width: int, height: int, out: pathlib.Path, transparent: bool = False) -> None:
            path = pathlib.Path(tmp) / "x.svg"
            path.write_text(svg, encoding="utf-8")
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(f"file://{path}")
            page.screenshot(path=str(out), omit_background=transparent)
            page.close()

        # Значки PWA: обычные со скруглением и прозрачными углами; maskable и iOS на всю площадь
        render(tile_svg(192), 192, 192, ROOT / "public/icons/icon-192.png", transparent=True)
        render(tile_svg(512), 512, 512, ROOT / "public/icons/icon-512.png", transparent=True)
        # Android обрезает maskable-значок по кругу или «капле»: букву уменьшаем, чтобы она осталась внутри
        render(tile_svg(512, rounded=False, glyph_scale=0.8), 512, 512, ROOT / "public/icons/icon-maskable-512.png")
        render(tile_svg(180, rounded=False), 180, 180, ROOT / "app/apple-icon.png")

        # favicon.ico из трёх размеров
        sizes = (16, 32, 48)
        frames = []
        for size in sizes:
            out = pathlib.Path(tmp) / f"f{size}.png"
            render(tile_svg(size), size, size, out, transparent=True)
            frames.append(Image.open(out).convert("RGBA"))
        frames[-1].save(ROOT / "app/favicon.ico", format="ICO", sizes=[(s, s) for s in sizes], append_images=frames[:-1])

        # Заставки запуска iPhone
        for width, height, ratio in IPHONES:
            w, h = width * ratio, height * ratio
            render(splash_svg(w, h, word_d, box), w, h, ROOT / f"public/splash/iphone-{w}x{h}.png")

        browser.close()
    print("Готово.")


if __name__ == "__main__":
    main()
