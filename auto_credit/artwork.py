"""Shared QImage artwork for preview and encoded output; no shell text filters."""
import math
import os
from pathlib import Path
from functools import lru_cache

import qrcode
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QImage, QPainter,
    QTextLayout, QTextOption,
)

from .models import Credit


@lru_cache(maxsize=1)
def ensure_fonts() -> None:
    # Windows' offscreen Qt backend has no native font database. Explicitly
    # register the OS fonts so headless renders contain real CJK/Latin glyphs.
    if not QFontDatabase.families() and os.name == "nt":
        folder = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("msjh.ttc", "msjhbd.ttc", "segoeui.ttf", "seguiemj.ttf"):
            path = folder / name
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))


def font(pixels: float, bold: bool = False) -> QFont:
    ensure_fonts()
    families = set(QFontDatabase.families())
    family = next((f for f in ("Microsoft JhengHei", "Noto Sans CJK TC", "PingFang TC", "Arial")
                   if f in families), "Sans Serif")
    result = QFont(family)
    result.setPixelSize(max(8, round(pixels)))
    result.setBold(bold)
    return result


def text_layout(text: str, face: QFont, width: float) -> tuple[QTextLayout, float]:
    layout = QTextLayout(text, face)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    layout.beginLayout()
    height = 0.0
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(width)
        line.setPosition(QPointF(0, height))
        height += line.height()
    layout.endLayout()
    return layout, height


def overlay(credit: Credit, width: int, height: int) -> QImage:
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    short = min(width, height)
    margin = max(8, short * .035)
    padding = max(5, short * .014)
    face = font(short * credit.font_percent / 100, True)
    max_width = width * .76 - 2 * padding
    layout, text_height = text_layout(credit.overlay_text, face, max_width)
    text_width = min(max_width, max(layout.lineAt(i).naturalTextWidth()
                                    for i in range(layout.lineCount())))
    box = QRectF(width - margin - text_width - 2 * padding, margin,
                 text_width + 2 * padding, text_height + 2 * padding)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(10, 15, 23, 180))
    painter.drawRoundedRect(box, padding * .65, padding * .65)
    painter.setPen(QColor("#ffffff"))
    layout.draw(painter, box.topLeft() + QPointF(padding, padding))
    painter.end()
    return image


def qr_image(url: str, desired_size: int) -> QImage:
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4)
    code.add_data(url)
    try:
        code.make(fit=True)
    except qrcode.exceptions.DataOverflowError:
        raise ValueError("原片連結的資料量超過 QR Code 容量，請縮短連結。") from None
    matrix = code.get_matrix()
    # Integer module sizes and a four-module quiet zone keep the QR sharp.
    module = max(2, math.ceil(desired_size / len(matrix)))
    size = len(matrix) * module
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#000000"))
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                painter.drawRect(x * module, y * module, module, module)
    painter.end()
    return image


def end_card(credit: Credit, width: int, height: int) -> QImage:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#111927"))
    short = min(width, height)
    margin = short * .075
    available = width - margin * 2
    qr = qr_image(credit.url, round(short * .24))
    # Fit the complete URL and author. Never truncate the encoded source text.
    size = max(10, short * .037)
    for _ in range(40):
        rows = []
        for text, multiplier, bold, color in (
            ("影片來源", 1.5, True, "#ffffff"),
            (f"平台：{credit.platform}", 1, False, "#b8c7da"),
            (f"原作者：{credit.author}", 1.08, True, "#ffffff"),
            ("原片連結", .8, False, "#71dbc4"),
            (credit.url, .75, False, "#b8c7da"),
        ):
            layout, row_height = text_layout(text, font(size * multiplier, bold), available)
            rows.append((layout, row_height, color))
        gap = size * .6
        total = sum(row[1] for row in rows) + gap * 5 + qr.height() + size * 1.5
        if total <= height - margin * 2 or size <= 8:
            break
        size *= .91
    if total > height - margin * 2 or qr.width() > available:
        raise ValueError("來源資料過長，無法在這個影片尺寸清楚顯示；請縮短連結或作者名稱。")
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    y = (height - total) / 2
    for layout, row_height, color in rows:
        painter.setPen(QColor(color))
        layout.draw(painter, QPointF(margin, y))
        y += row_height + gap
    painter.drawImage(QPointF(margin, y), qr)
    painter.setPen(QColor("#8193aa"))
    painter.setFont(font(size * .7))
    painter.drawText(QPointF(margin, y + qr.height() + size * 1.25), "掃描 QR Code 查看原片")
    painter.end()
    return image


def composite(frame: QImage, watermark: QImage) -> QImage:
    image = frame.convertToFormat(QImage.Format.Format_RGB32)
    painter = QPainter(image)
    painter.drawImage(0, 0, watermark)
    painter.end()
    return image
