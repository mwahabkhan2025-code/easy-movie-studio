"""The multi-track timeline: a row per track, clips positioned by real time, a ruler,
a playhead, drag-to-reposition (with snapping) on non-ripple tracks, and drag-and-drop
import onto a specific track's row.

This is a second, independent view of the same project (alongside the storyboard),
switched via the status bar's view toggle. It keeps its own selection list with the
same signal contract as StoryboardView so MainWindow can treat either view uniformly.
"""

from __future__ import annotations

import os
import zlib
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QTextOption
from PySide6.QtWidgets import QMenu, QWidget

from ..model import Clip, Project, Track
from .theme import COLORS
from .timeline_layout import (ROW_HEIGHT, RULER_HEIGHT, collect_snap_anchors, row_at_y, row_top,
                              snap_time, time_to_x, x_to_time)

MIN_PPS, MAX_PPS, DEFAULT_PPS = 3.0, 60.0, 16.0
SNAP_PIXELS = 10.0  # drag-snap catch radius, in screen pixels

_TRACK_HUES = {"main_video": 110, "overlay_video": 270, "audio": 205}


class TimelineView(QWidget):
    selectionChanged = Signal()
    commandRequested = Signal(str)
    moveRequested = Signal(str, float)            # clip id, new start time
    seekRequested = Signal(float)
    mediaDropped = Signal(str, float, list)        # track id, start time, file paths

    def __init__(self, project: Project, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.project = project
        self.selected: List[str] = []
        self.pps = DEFAULT_PPS
        self.playhead_time = 0.0
        self.setMinimumHeight(200)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self._drag: Optional[dict] = None
        self._update_size()

    # ---- model access -----------------------------------------------------
    def set_project(self, project: Project) -> None:
        self.project = project
        self.selected = []
        self.refresh()

    def refresh(self) -> None:
        all_ids = {c.id for t in self.project.tracks for c in t.clips}
        self.selected = [i for i in self.selected if i in all_ids]
        self._update_size()
        self.update()

    def set_selection(self, ids: List[str]) -> None:
        self.selected = list(ids)
        self.update()
        self.selectionChanged.emit()

    def set_time(self, t: float) -> None:
        self.playhead_time = t
        self.update()

    def set_pps(self, pps: float) -> None:
        self.pps = max(MIN_PPS, min(MAX_PPS, pps))
        self._update_size()
        self.update()

    # ---- geometry -----------------------------------------------------------
    def _tracks(self) -> List[Track]:
        return list(self.project.tracks)

    def _placements(self) -> List[List[Tuple[Clip, float, float]]]:
        """Per track, a list of (clip, start, end) using each track's own layout."""
        return [[(p.clip, p.start, p.end) for p in track.layout()] for track in self._tracks()]

    def _track_kind_key(self, track: Track) -> str:
        if track is self.project.main_track:
            return "main_video"
        return "overlay_video" if track.kind == "video" else "audio"

    def _total_duration(self) -> float:
        return max((t.duration for t in self._tracks()), default=0.0)

    def _update_size(self) -> None:
        tracks = self._tracks()
        width = time_to_x(self._total_duration(), self.pps) + 120
        height = row_top(len(tracks)) + 20
        self.setMinimumSize(int(width), int(height))

    def _clip_rect(self, start: float, end: float, row: int) -> QRectF:
        x0, x1 = time_to_x(start, self.pps), time_to_x(end, self.pps)
        return QRectF(x0, row_top(row) + 1, max(4.0, x1 - x0), ROW_HEIGHT - 2)

    def _hit_test(self, pos) -> Optional[Tuple[int, Clip, float, float]]:
        row = row_at_y(pos.y(), len(self._tracks()))
        if row is None:
            return None
        for clip, start, end in self._placements()[row]:
            if time_to_x(start, self.pps) <= pos.x() <= time_to_x(end, self.pps):
                return row, clip, start, end
        return None

    # ---- interaction --------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        if pos.y() < RULER_HEIGHT:
            self.seekRequested.emit(x_to_time(pos.x(), self.pps))
            return
        hit = self._hit_test(pos)
        if hit is None:
            if self.selected:
                self.set_selection([])
            return
        row, clip, start, end = hit
        track = self._tracks()[row]
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            ids = [i for i in self.selected if i != clip.id]
            if clip.id not in self.selected:
                ids.append(clip.id)
            self.set_selection(ids)
        else:
            self.set_selection([clip.id])
        if not track.ripple:
            self._drag = {"clip_id": clip.id, "track": track, "press_x": pos.x(),
                         "orig_start": start, "duration": end - start}
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        if self._drag is not None:
            self._update_drag(pos.x())
            return
        hit = self._hit_test(pos)
        self.setToolTip(self._tooltip_for(hit[1]) if hit else "")
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or self._drag is None:
            return
        state = self._drag
        self._drag = None
        self.unsetCursor()
        clip = next((c for t in self.project.tracks for c in t.clips
                    if c.id == state["clip_id"]), None)
        if clip is None:
            return
        final_start = clip.start
        clip.start = state["orig_start"]  # revert the live preview; MainWindow applies a command
        self.update()
        if abs(final_start - state["orig_start"]) > 1e-6:
            self.moveRequested.emit(state["clip_id"], final_start)

    def _update_drag(self, x: float) -> None:
        state = self._drag
        track = state["track"]
        candidate = x_to_time(x - (state["press_x"] - time_to_x(state["orig_start"], self.pps)),
                              self.pps)
        others = [[(start, end) for c, start, end in spans if c.id != state["clip_id"]]
                 for spans in self._placements()]
        anchors = collect_snap_anchors(others, extra=[self.playhead_time])
        threshold = SNAP_PIXELS / self.pps
        snapped_start = snap_time(candidate, anchors, threshold)
        # also let the clip's own trailing edge snap, which feels more natural when
        # dragging a clip up against another clip's start from the left
        snapped_end = snap_time(candidate + state["duration"], anchors, threshold)
        if snapped_end != candidate + state["duration"] and snapped_start == candidate:
            snapped_start = snapped_end - state["duration"]
        clip = next((c for c in track.clips if c.id == state["clip_id"]), None)
        if clip is not None:
            clip.start = max(0.0, snapped_start)
            self._update_size()
            self.update()

    def _tooltip_for(self, clip: Clip) -> str:
        from ..util import format_time
        return f"{os.path.basename(clip.source) or clip.text or clip.kind}\n" \
              f"Length: {format_time(clip.duration)}"

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        hit = self._hit_test(event.pos())
        if hit is None:
            return
        _row, clip, _start, _end = hit
        track = next(t for t in self.project.tracks if clip.id in {c.id for c in t.clips})
        if clip.id not in self.selected:
            self.set_selection([clip.id])
        menu = QMenu(self)
        if track is not self.project.main_track and track.kind == "video":
            menu.addAction("Picture-in-picture position...").setData("edit.overlay_position")
            menu.addSeparator()
        menu.addAction("Remove").setData("home.remove")
        menu.addAction("Properties").setData("edit.properties")
        chosen = menu.exec(event.globalPos())
        if chosen is not None:
            self.commandRequested.emit(str(chosen.data()))

    # ---- drag and drop onto a specific row -----------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        row = row_at_y(event.position().y(), len(self._tracks()))
        if row is None:
            event.ignore()  # let MainWindow's own handler fall back to the main track
            return
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if not paths:
            return
        event.acceptProposedAction()
        track = self._tracks()[row]
        start_time = x_to_time(event.position().x(), self.pps)
        self.mediaDropped.emit(track.id, start_time, paths)

    # ---- painting -----------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_ruler(painter)
        tracks = self._tracks()
        placements = self._placements()
        for row, track in enumerate(tracks):
            self._paint_row_label(painter, track, row)
            for clip, start, end in placements[row]:
                self._paint_clip(painter, clip, track, start, end, row)
        self._paint_playhead(painter)
        painter.end()

    def _paint_ruler(self, painter: QPainter) -> None:
        painter.fillRect(QRectF(0, 0, self.width(), RULER_HEIGHT), QColor("#eef1f4"))
        painter.setPen(QColor(COLORS["text_muted"]))
        step = 5 if self.pps < 20 else 1
        t = 0.0
        while time_to_x(t, self.pps) < self.width():
            x = time_to_x(t, self.pps)
            painter.drawLine(QPointF(x, RULER_HEIGHT - 6), QPointF(x, RULER_HEIGHT))
            painter.drawText(QPointF(x + 2, RULER_HEIGHT - 8), f"{int(t)}s")
            t += step

    def _paint_row_label(self, painter: QPainter, track: Track, row: int) -> None:
        rect = QRectF(0, row_top(row), 68, ROW_HEIGHT)
        painter.fillRect(rect, QColor("#f5f6f8"))
        painter.setPen(QColor(COLORS["text"]))
        font = QFont()
        font.setPointSizeF(7.5)
        painter.setFont(font)
        painter.drawText(rect.adjusted(4, 0, -2, 0), track.name or track.kind,
                         QTextOption(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))

    def _paint_clip(self, painter: QPainter, clip: Clip, track: Track, start: float, end: float,
                    row: int) -> None:
        rect = self._clip_rect(start, end, row)
        hue = _TRACK_HUES[self._track_kind_key(track)]
        jitter = zlib.crc32(clip.id.encode("utf-8")) % 20 - 10
        color = QColor.fromHsv(max(0, min(359, hue + jitter)), 110, 185)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(rect, 3, 3)

        label = clip.text or os.path.basename(clip.source) or clip.kind
        font = QFont()
        font.setPointSizeF(7.5)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        text_rect = rect.adjusted(4, 2, -4, -2)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(text_rect, metrics.elidedText(label, Qt.TextElideMode.ElideRight,
                                                        int(text_rect.width())))
        if clip.id in self.selected:
            painter.setPen(QPen(QColor(COLORS["select_blue"]), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 3, 3)

    def _paint_playhead(self, painter: QPainter) -> None:
        x = time_to_x(self.playhead_time, self.pps)
        painter.setPen(QPen(QColor("#e24b4b"), 1.5))
        painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
