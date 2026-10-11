"""The storyboard: clips of the main video track shown as film-strip blocks."""

from __future__ import annotations

import math
import os
import random
import zlib
from typing import Dict, List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter,
                           QPen, QTextOption)
from PySide6.QtWidgets import QMenu, QWidget

from ..model import Clip, Project
from ..model.clip import STATIC_KINDS
from ..util import format_time
from .icons import icon
from ..model.clip import MIN_SOURCE_LENGTH
from .storyboard_layout import (cover_source_rect, edge_hit, hit_test, insertion_index,
                                layout_clips)
from .theme import COLORS
from .thumbcache import ThumbnailCache

THUMB_HEIGHTS = {"xl": 96, "l": 72, "m": 52, "s": 36}
DEFAULT_PPS = 14.0
MIN_PPS, MAX_PPS = 3.0, 60.0
_EDGE = 9  # width of the perforation margin on each side of a block


class StoryboardView(QWidget):
    selectionChanged = Signal()
    addMediaRequested = Signal()
    commandRequested = Signal(str)
    reorderRequested = Signal(str, int)                       # clip id, new index
    trimFinished = Signal(str, float, float, float, float)     # clip id, old in, old out, new in, new out
    trimLive = Signal()                                        # fires repeatedly while dragging an edge

    def __init__(self, project: Project, thumbs: Optional[ThumbnailCache] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.project = project
        self.thumbs = thumbs
        self.selected: List[str] = []
        self.problems: Dict[str, str] = {}  # media path -> reason it cannot be read
        self.pps = DEFAULT_PPS
        self.thumb_h = THUMB_HEIGHTS["m"]
        self.show_waveforms = True
        self.setMinimumHeight(200)
        self.setMouseTracking(True)
        if thumbs is not None:
            thumbs.ready.connect(self.update)
        self.trim_mode = False
        self._edge_drag = None   # dict while an edge is being dragged
        self._reorder = None     # dict while a clip is being dragged to reorder
        self._press = None       # (clip_id, index, QPointF) recorded on press, before a drag starts
        self._insert_marker = None  # x position (float) to draw while reordering, or None

    # ---- model access -----------------------------------------------------
    def clips(self) -> List[Clip]:
        return list(self.project.main_track.clips)

    def set_project(self, project: Project) -> None:
        self.project = project
        self.selected = []
        self.problems = {}
        self.refresh()

    def set_problems(self, problems: Dict[str, str]) -> None:
        self.problems = dict(problems)
        self.update()

    def refresh(self) -> None:
        ids = {c.id for c in self.clips()}
        self.selected = [i for i in self.selected if i in ids]
        self._update_height()
        self.update()

    def select_all(self) -> None:
        self.selected = [c.id for c in self.clips()]
        self.update()
        self.selectionChanged.emit()

    def set_selection(self, ids: List[str]) -> None:
        self.selected = list(ids)
        self.update()
        self.selectionChanged.emit()

    # ---- view settings ----------------------------------------------------
    def set_pps(self, pps: float) -> None:
        self.pps = max(MIN_PPS, min(MAX_PPS, pps))
        self._update_height()
        self.update()

    def set_thumb_size(self, key: str) -> None:
        self.thumb_h = THUMB_HEIGHTS[key]
        self._update_height()
        self.update()

    def set_show_waveforms(self, show: bool) -> None:
        self.show_waveforms = show
        self.update()

    def set_trim_mode(self, active: bool) -> None:
        self.trim_mode = active
        if not active:
            self._edge_drag = None
        self.update()

    # ---- geometry ---------------------------------------------------------
    def _layout(self):
        clips = self.clips()
        rects, height = layout_clips([c.duration for c in clips], self.pps,
                                     float(self.width()), float(self.thumb_h))
        return clips, rects, height

    def _update_height(self) -> None:
        _, _, height = self._layout()
        self.setMinimumHeight(max(200, int(height) + 4))

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._update_height()

    # ---- interaction --------------------------------------------------------
    DRAG_THRESHOLD = 6.0

    def _clip_at(self, pos) -> int:
        _, rects, _ = self._layout()
        return hit_test(rects, pos.x(), pos.y())

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        clips = self.clips()
        pos = event.position()
        index = self._clip_at(pos)
        if index < 0:
            if not clips:
                self.addMediaRequested.emit()
            elif self.selected:
                self.set_selection([])
            return
        clip = clips[index]

        if (self.trim_mode and len(self.selected) == 1 and self.selected[0] == clip.id
                and clip.media_duration is not None):
            _, rects, _ = self._layout()
            edge = edge_hit(rects[index], pos.x())
            if edge is not None:
                self.begin_edge_drag(clip.id, edge)
                return

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            ids = [i for i in self.selected if i != clip.id]
            if clip.id not in self.selected:
                ids.append(clip.id)
            self.set_selection(ids)
        else:
            self.set_selection([clip.id])
            if not self.trim_mode:
                self._press = (clip.id, index, pos)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        if self._edge_drag is not None:
            self.update_edge_drag(pos.x())
            return
        if self._reorder is not None:
            self.update_reorder(pos.x(), pos.y())
            return
        if (self._press is not None and event.buttons() & Qt.MouseButton.LeftButton
                and not self.trim_mode):
            clip_id, index, start_pos = self._press
            if (pos - start_pos).manhattanLength() >= self.DRAG_THRESHOLD:
                self._press = None
                self.begin_reorder(clip_id)
                self.update_reorder(pos.x(), pos.y())
                return
        clips = self.clips()
        index = self._clip_at(pos)
        self.setToolTip(self.tooltip_for(clips[index]) if index >= 0 else "")
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._press = None
        if self._edge_drag is not None:
            self.end_edge_drag()
        elif self._reorder is not None:
            self.end_reorder()

    # ---- edge-drag trimming (Trim tool) --------------------------------------
    def begin_edge_drag(self, clip_id: str, edge: str) -> None:
        clip = self.project.main_track.get_clip(clip_id)
        self._edge_drag = {"clip_id": clip_id, "edge": edge, "old_in": clip.src_in,
                           "old_out": clip.src_out, "start_x": None}
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    def update_edge_drag(self, px: float) -> None:
        state = self._edge_drag
        if state is None:
            return
        clip = self.project.main_track.get_clip(state["clip_id"])
        if state["start_x"] is None:
            state["start_x"] = px
        delta_src = (px - state["start_x"]) * clip.speed / self.pps
        try:
            if state["edge"] == "left":
                new_in = max(0.0, min(state["old_in"] + delta_src,
                                      clip.src_out - MIN_SOURCE_LENGTH))
                clip.trim(src_in=new_in)
            else:
                limit = clip.media_duration if clip.media_duration is not None else clip.src_out
                new_out = max(clip.src_in + MIN_SOURCE_LENGTH,
                              min(state["old_out"] + delta_src, limit))
                clip.trim(src_out=new_out)
        except ValueError:
            pass
        self._update_height()
        self.update()
        self.trimLive.emit()

    def end_edge_drag(self) -> None:
        state = self._edge_drag
        self._edge_drag = None
        self.unsetCursor()
        if state is None or state["start_x"] is None:
            return
        clip = self.project.main_track.get_clip(state["clip_id"])
        new_in, new_out = clip.src_in, clip.src_out
        if (new_in, new_out) != (state["old_in"], state["old_out"]):
            clip.trim(src_in=state["old_in"], src_out=state["old_out"])  # revert the live preview
            self.trimFinished.emit(state["clip_id"], state["old_in"], state["old_out"],
                                   new_in, new_out)
        self.update()

    # ---- drag to reorder --------------------------------------------------------
    def begin_reorder(self, clip_id: str) -> None:
        self._reorder = {"clip_id": clip_id, "target": None}
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def update_reorder(self, px: float, py: float) -> None:
        state = self._reorder
        if state is None:
            return
        clips = self.clips()
        others = [c.duration for c in clips if c.id != state["clip_id"]]
        rects, _ = layout_clips(others, self.pps, float(self.width()), float(self.thumb_h))
        target = insertion_index(rects, px, py)
        state["target"] = target
        self._insert_marker = rects[target][0] - 4.0 if target < len(rects) else (
            rects[-1][0] + rects[-1][2] + 4.0 if rects else 12.0)
        self.update()

    def end_reorder(self) -> None:
        state = self._reorder
        self._reorder = None
        self._insert_marker = None
        self.unsetCursor()
        self.update()
        if state is None or state["target"] is None:
            return
        clip_id = state["clip_id"]
        current = self.project.main_track.index_of(clip_id)
        target = state["target"]
        if target != current and target != current + 1:
            self.reorderRequested.emit(clip_id, target)

    def tooltip_for(self, clip: Clip) -> str:
        lines = [os.path.basename(clip.source), f"Length: {format_time(clip.duration)}"]
        if clip.transition_in is not None:
            lines.append(f"Transition: {clip.transition_in.name} "
                         f"({clip.transition_in.duration:g}s)")
        if clip.effect:
            lines.append(f"Effect: {clip.effect}")
        if clip.pan_zoom:
            lines.append(f"Pan and zoom: {clip.pan_zoom}")
        if abs(clip.brightness) > 1e-6:
            lines.append(f"Brightness: {clip.brightness:+.2f}")
        if clip.source in self.problems:
            lines.append(f"Problem: {self.problems[clip.source]}")
        return "\n".join(lines)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        clips = self.clips()
        index = self._clip_at(event.pos())
        if index < 0:
            return
        if clips[index].id not in self.selected:
            self.set_selection([clips[index].id])
        menu = QMenu(self)
        for text, command in (("Rotate left", "home.rotate_left"),
                              ("Rotate right", "home.rotate_right"),
                              ("Remove", "home.remove"), (None, None),
                              ("Properties", "edit.properties")):
            if text is None:
                menu.addSeparator()
            else:
                menu.addAction(text).setData(command)
        chosen = menu.exec(event.globalPos())
        if chosen is not None:
            self.commandRequested.emit(str(chosen.data()))

    # ---- painting -----------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clips, rects, _ = self._layout()
        if not clips:
            self._paint_empty(painter)
        else:
            for clip, rect in zip(clips, rects):
                self._paint_clip(painter, clip, QRectF(*rect))
                if (self.trim_mode and len(self.selected) == 1 and clip.id == self.selected[0]
                        and clip.media_duration is not None):
                    self._paint_edge_handles(painter, QRectF(*rect))
        if self._insert_marker is not None:
            self._paint_insert_marker(painter)
        painter.end()

    def _paint_edge_handles(self, painter: QPainter, rect: QRectF) -> None:
        handle_w = 7.0
        color = QColor(COLORS["select_blue"])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(rect.left(), rect.top(), handle_w, rect.height()), 2, 2)
        painter.drawRoundedRect(QRectF(rect.right() - handle_w, rect.top(), handle_w,
                                       rect.height()), 2, 2)
        painter.setPen(QPen(QColor("#ffffff"), 1.4))
        for x in (rect.left() + handle_w / 2, rect.right() - handle_w / 2):
            painter.drawLine(QPointF(x, rect.top() + rect.height() * 0.35),
                             QPointF(x, rect.top() + rect.height() * 0.65))

    def _paint_insert_marker(self, painter: QPainter) -> None:
        x = self._insert_marker
        color = QColor(COLORS["select_blue"])
        painter.setPen(QPen(color, 3))
        painter.drawLine(QPointF(x, 8), QPointF(x, self.thumb_h + 16))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        for y in (8, self.thumb_h + 16):
            painter.drawEllipse(QPointF(x, y), 3.5, 3.5)

    def _paint_empty(self, painter: QPainter) -> None:
        area = QRectF(self.rect()).adjusted(10, 10, -10, -10)
        pen = QPen(QColor(COLORS["dash_blue"]), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(area)
        pixmap = icon("mdi6.movie-open-plus-outline", COLORS["dash_blue"]).pixmap(56, 56)
        cx = area.center().x()
        cy = area.center().y()
        painter.drawPixmap(int(cx - 28), int(cy - 50), pixmap)
        painter.setPen(QColor(COLORS["text_muted"]))
        painter.drawText(QRectF(area.left(), cy + 14, area.width(), 24),
                         "Click here to browse for videos and photos",
                         QTextOption(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop))

    def _paint_thumbnails(self, painter: QPainter, clip: Clip, rect: QRectF) -> None:
        inner = rect.adjusted(_EDGE, 0, -_EDGE, 0)
        if self.thumbs is None or inner.width() < 8:
            return
        tile_w = self.thumb_h * 16 / 9
        count = max(1, math.ceil(inner.width() / tile_w))
        pixel_h = int(self.thumb_h * max(1.0, self.devicePixelRatioF()))
        span = clip.src_out - clip.src_in
        step = inner.width() / count
        for i in range(count):
            if clip.kind in STATIC_KINDS:
                time = None
            else:
                time = clip.src_in + (i + 0.5) / count * span
            image = self.thumbs.get(clip.source, time, pixel_h, clip.rotation)
            if image is None:
                continue
            target = QRectF(inner.left() + i * step, inner.top(), step, inner.height())
            sx, sy, sw, sh = cover_source_rect(image.width(), image.height(),
                                               target.width(), target.height())
            painter.drawImage(target, image, QRectF(sx, sy, sw, sh))

    def _paint_transition_badge(self, painter: QPainter, rect: QRectF) -> None:
        """A small chevron at a clip's left edge, showing it has an incoming transition."""
        x = rect.left() + _EDGE + 3
        cy = rect.top() + rect.height() / 2
        size = min(9.0, rect.height() * 0.3)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#f5a623"))
        painter.drawPolygon([QPointF(x, cy - size), QPointF(x + size, cy),
                             QPointF(x, cy + size)])

    def _paint_fx_badge(self, painter: QPainter, rect: QRectF) -> None:
        """A small purple dot in the top-right corner, showing an effect/pan-zoom/brightness
        change is applied, since the storyboard thumbnail itself doesn't render the effect."""
        radius = min(5.0, rect.height() * 0.14)
        cx, cy = rect.right() - _EDGE - radius - 2, rect.top() + radius + 3
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.setBrush(QColor("#8e44ad"))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

    def _paint_caption_badge(self, painter: QPainter, rect: QRectF) -> None:
        """A small "CC" tag in the bottom-right corner for a clip with a burned-in caption."""
        if rect.width() < 30:
            return
        w, h = min(20.0, rect.width() * 0.3), 12.0
        badge = QRectF(rect.right() - _EDGE - w - 2, rect.bottom() - h - 3, w, h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(20, 20, 20, 210))
        painter.drawRoundedRect(badge, 2, 2)
        font = QFont()
        font.setPointSizeF(6.5)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(badge, "CC", QTextOption(Qt.AlignmentFlag.AlignCenter))

    def _paint_clip(self, painter: QPainter, clip: Clip, rect: QRectF) -> None:
        hue = 95 + zlib.crc32(clip.source.encode("utf-8")) % 60
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0, QColor.fromHsv(hue, 60, 150))
        gradient.setColorAt(1, QColor.fromHsv(hue, 90, 90))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawRect(rect)

        broken = clip.source in self.problems
        if not broken:
            self._paint_thumbnails(painter, clip, rect)

        painter.setBrush(QColor("#101418"))  # film-strip perforations
        painter.drawRect(QRectF(rect.left(), rect.top(), _EDGE - 1, rect.height()))
        painter.drawRect(QRectF(rect.right() - _EDGE + 1, rect.top(), _EDGE - 1, rect.height()))
        painter.setBrush(QColor("#d9dde2"))
        y = rect.top() + 5
        while y < rect.bottom() - 8:
            painter.drawRect(QRectF(rect.left() + 2, y, 4, 5))
            painter.drawRect(QRectF(rect.right() - 6, y, 4, 5))
            y += 9

        if self.show_waveforms and rect.height() >= 40 and not broken:
            rng = random.Random(clip.id)
            base = rect.bottom() - 3
            painter.setPen(QPen(QColor(255, 255, 255, 190), 1))
            x = rect.left() + _EDGE + 2
            while x < rect.right() - _EDGE - 2:
                h = 2 + rng.random() * (rect.height() * 0.22)
                painter.drawLine(QPointF(x, base), QPointF(x, base - h))
                x += 2

        if clip.transition_in is not None:
            self._paint_transition_badge(painter, rect)
        if clip.effect or clip.pan_zoom or abs(clip.brightness) > 1e-6:
            self._paint_fx_badge(painter, rect)
        if clip.caption_text.strip():
            self._paint_caption_badge(painter, rect)

        font = QFont()
        font.setPointSizeF(8)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        name = os.path.basename(clip.source)
        label_rect = QRectF(rect.left() + _EDGE + 3, rect.top() + 3,
                            rect.width() - 2 * _EDGE - 6, 16)
        text = metrics.elidedText(name, Qt.TextElideMode.ElideRight, int(label_rect.width()))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 120))
        painter.drawRoundedRect(QRectF(label_rect.left() - 2, label_rect.top(),
                                       min(label_rect.width(), metrics.horizontalAdvance(text) + 6),
                                       15), 3, 3)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(label_rect, text)
        if clip.rotation:
            painter.drawText(QRectF(label_rect.left(), rect.top() + 19, 60, 14),
                             f"\u21bb {clip.rotation}\u00b0")

        if broken:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(170, 30, 30, 170))
            painter.drawRect(rect.adjusted(_EDGE, rect.height() / 2 - 10, -_EDGE,
                                           -(rect.height() / 2 - 10)))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(QRectF(rect.left(), rect.center().y() - 10, rect.width(), 20),
                             "Can't read this file",
                             QTextOption(Qt.AlignmentFlag.AlignCenter))

        if clip.id in self.selected:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(COLORS["select_blue"]), 2))
            painter.drawRect(rect.adjusted(-1, -1, 1, 1))
