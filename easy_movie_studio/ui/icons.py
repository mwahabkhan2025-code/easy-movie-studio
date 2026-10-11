"""Icon loading. Uses qtawesome (Material Design Icons, tinted Movie Maker blue).

If qtawesome or a specific glyph is unavailable, a simple drawn placeholder is
used instead, so a wrong icon name never crashes the app.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPen,
                           QPixmap, QTextOption)

from .theme import COLORS


def _fallback_icon(name: str, color: str) -> QIcon:
    size = 32
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 2))
    painter.drawRoundedRect(QRectF(3, 3, size - 6, size - 6), 5, 5)
    font = QFont()
    font.setPixelSize(16)
    font.setBold(True)
    painter.setFont(font)
    letter = (name.split(".")[-1][:1] or "?").upper()
    painter.drawText(QRectF(0, 0, size, size), letter, QTextOption(Qt.AlignmentFlag.AlignCenter))
    painter.end()
    return QIcon(pixmap)


@lru_cache(maxsize=None)
def icon(name: str, color: Optional[str] = None) -> QIcon:
    color = color or COLORS["icon"]
    try:
        import qtawesome as qta
        return qta.icon(name, color=color, color_disabled=COLORS["icon_disabled"])
    except Exception:  # missing package or unknown glyph
        return _fallback_icon(name, color)


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    """The application icon: a rounded blue tile with a white filmstrip glyph.

    Original artwork (not a copy of Windows Movie Maker's icon), built at several
    sizes so Windows picks a crisp one for the title bar, taskbar and alt-tab.
    """
    result = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        margin = max(1.0, size * 0.045)
        rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
        gradient = QLinearGradient(0, 0, 0, size)
        gradient.setColorAt(0, QColor(COLORS["file_blue_hover"]))
        gradient.setColorAt(1, QColor(COLORS["file_blue_pressed"]))
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor(COLORS["file_blue_pressed"]), max(1.0, size * 0.035)))
        painter.drawRoundedRect(rect, size * 0.22, size * 0.22)
        try:
            import qtawesome as qta
            glyph = qta.icon("mdi6.movie-open-outline", color="white")                 .pixmap(int(size * 0.6), int(size * 0.6))
            painter.drawPixmap(int((size - glyph.width()) / 2), int((size - glyph.height()) / 2),
                               glyph)
        except Exception:
            painter.setPen(QPen(QColor("#ffffff"), max(1.0, size * 0.07)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            inset = size * 0.28
            painter.drawRoundedRect(QRectF(inset, inset, size - 2 * inset, size - 2 * inset),
                                    size * 0.06, size * 0.06)
        painter.end()
        result.addPixmap(pixmap)
    return result
