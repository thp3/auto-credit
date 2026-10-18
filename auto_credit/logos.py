"""User-provided platform logos, shared by previews and encoded end cards."""
from functools import lru_cache
from importlib.resources import files

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


LOGOS = {"youtube": "youtube.svg", "bilibili": "bilibili.png", "tiktok": "tiktok.png"}
ALIASES = {"yt": "youtube", "哔哩哔哩": "bilibili", "嗶哩嗶哩": "bilibili", "b站": "bilibili"}


@lru_cache(maxsize=3)
def _load_logo(platform: str) -> QImage:
    filename = LOGOS[platform]
    data = files("auto_credit").joinpath("assets", "logos", filename).read_bytes()
    if filename.endswith(".svg"):
        renderer = QSvgRenderer(data)
        if not renderer.isValid():
            raise ValueError(f"平台 logo 無法讀取：{filename}")
        image = QImage(renderer.defaultSize(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
    else:
        image = QImage.fromData(data)
    if image.isNull():
        raise ValueError(f"平台 logo 無法讀取：{filename}")
    # Ignore transparent outer padding for layout only. Original assets remain
    # unchanged; opaque backgrounds (including TikTok's black tile) are kept.
    left, top, right, bottom = image.width(), image.height(), -1, -1
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha():
                left, top = min(left, x), min(top, y)
                right, bottom = max(right, x), max(bottom, y)
    if right < left:
        raise ValueError(f"平台 logo 沒有可見內容：{filename}")
    return image.copy(QRect(left, top, right - left + 1, bottom - top + 1))


def platform_logo(platform: str) -> QImage | None:
    key = "".join(platform.casefold().split())
    key = ALIASES.get(key, key)
    if key not in LOGOS:
        return None
    # QImage is implicitly shared; callers cannot mutate the cached image.
    return QImage(_load_logo(key))
