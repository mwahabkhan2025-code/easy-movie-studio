"""Playback controller: plays the main video track in the preview.

Videos are decoded by Qt Multimedia (QMediaPlayer -> QVideoSink), so each frame
arrives here as a QImage that we can rotate, letterbox and later apply effects
to. Photos are shown for their duration using a timer. The controller keeps a
single *timeline time* and hides which clip is currently loaded.
"""

from __future__ import annotations

import os
import time as _time
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QImage, QImageReader, QTransform

from ..engine.playback_plan import (Segment, build_segments, clamp_time, segment_index_at,
                                    signature, step_time, total_duration)
from ..model import Project
from ..model.clip import STATIC_KINDS

try:  # Qt Multimedia ships with the normal PySide6 wheel, but degrade gracefully
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
    HAVE_MULTIMEDIA = True
except ImportError:  # pragma: no cover
    HAVE_MULTIMEDIA = False

_STILL_INTERVAL_MS = 33
_MAX_STILLS = 6


class PlaybackController(QObject):
    frameReady = Signal(QImage)
    timeChanged = Signal(float)   # timeline seconds
    stateChanged = Signal(bool)   # True while playing
    failed = Signal(str)          # human-readable problem

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._segments: List[Segment] = []
        self._signature: tuple = ()
        self._index = -1
        self._time = 0.0
        self._playing = False
        self._fps = 30.0
        self.has_frame = False

        self._stills: Dict[str, QImage] = {}
        self._still_clock = (0.0, 0.0)  # (monotonic start, timeline time at start)
        self._still_timer = QTimer(self)
        self._still_timer.setInterval(_STILL_INTERVAL_MS)
        self._still_timer.timeout.connect(self._tick_still)

        self._loaded_source: Optional[str] = None
        self._status_ready = False
        self._pending: Optional[tuple] = None  # (target_ms, play)
        self._settling = False
        self._settle_target = 0
        self._reported_unavailable = False
        self._proxy_resolver = None  # Optional[Callable[[str], str]]; see set_proxy_resolver

        self.available = HAVE_MULTIMEDIA
        if HAVE_MULTIMEDIA:
            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._player.setAudioOutput(self._audio)
            self._sink = QVideoSink(self)
            self._player.setVideoSink(self._sink)
            self._sink.videoFrameChanged.connect(self._on_frame)
            self._player.positionChanged.connect(self._on_position)
            self._player.mediaStatusChanged.connect(self._on_status)
            self._player.errorOccurred.connect(self._on_error)

    # ---- state ------------------------------------------------------------
    @property
    def time(self) -> float:
        return self._time

    @property
    def duration(self) -> float:
        return total_duration(self._segments)

    @property
    def playing(self) -> bool:
        return self._playing

    @property
    def current_segment(self) -> Optional[Segment]:
        if 0 <= self._index < len(self._segments):
            return self._segments[self._index]
        return None

    # ---- proxies ------------------------------------------------------------
    def set_proxy_resolver(self, resolver) -> None:
        """``resolver(source_path) -> path to actually play``, or None to always play the
        real source. Export never goes through this -- it's preview-only. Forces the
        currently-loaded video to reopen so a just-toggled-on proxy takes effect right away."""
        self._proxy_resolver = resolver
        self._loaded_source = None

    def _resolve_source(self, source: str) -> str:
        if self._proxy_resolver is None:
            return source
        try:
            return self._proxy_resolver(source) or source
        except Exception:
            return source

    # ---- project ------------------------------------------------------------
    def set_project(self, project: Project) -> None:
        """Rebuild from the project. Does nothing (and keeps playing) if nothing that
        affects playback changed; otherwise playback pauses at the same time."""
        self._fps = project.settings.fps
        segments = build_segments(project.main_track)
        sig = signature(segments)
        if sig == self._signature:
            return
        self._signature = sig
        was_playing = self._playing
        self._segments = segments
        self.has_frame = False
        self._pause_media()
        self._playing = False
        self._loaded_source = None
        self._status_ready = False
        self._pending = None
        if was_playing:
            self.stateChanged.emit(False)
        if not segments:
            self._index = -1
            self._time = 0.0
            self.timeChanged.emit(0.0)
            return
        self._time = clamp_time(segments, self._time)
        self._load(segment_index_at(segments, self._time), self._time, play=False)

    # ---- transport ------------------------------------------------------------
    def play(self) -> None:
        if not self._segments or self._playing:
            return
        t = 0.0 if self._time >= self.duration - 0.02 else self._time
        self._load(segment_index_at(self._segments, t), t, play=True)

    def pause(self) -> None:
        if not self._playing:
            return
        self._playing = False
        self._pause_media()
        self.stateChanged.emit(False)

    def toggle(self) -> None:
        if self._playing:
            self.pause()
        else:
            self.play()

    def seek(self, t: float) -> None:
        if not self._segments:
            return
        t = clamp_time(self._segments, t)
        self._load(segment_index_at(self._segments, t), t, play=self._playing)

    def step(self, direction: int) -> None:
        """Move one frame forward (+1) or back (-1), pausing playback."""
        self.pause()
        self.seek(step_time(self._time, self._fps, direction))

    def shutdown(self) -> None:
        self._still_timer.stop()
        if HAVE_MULTIMEDIA:
            self._player.stop()

    # ---- loading a segment ------------------------------------------------------
    def _pause_media(self) -> None:
        self._still_timer.stop()
        if HAVE_MULTIMEDIA and self._loaded_source is not None:
            self._player.pause()

    def _set_playing(self, playing: bool) -> None:
        if playing != self._playing:
            self._playing = playing
            self.stateChanged.emit(playing)

    def _load(self, index: int, t: float, play: bool) -> None:
        segment = self._segments[index]
        self._index = index
        self._time = t
        self._still_timer.stop()
        self._set_playing(play)
        self.timeChanged.emit(t)

        clip = segment.clip
        if clip.kind in STATIC_KINDS:
            if HAVE_MULTIMEDIA and self._loaded_source is not None:
                self._player.pause()
            image = self._still(clip.source)
            if image is None:
                self._fail(f"Can't read {os.path.basename(clip.source)}", quiet=not play)
                return
            self._emit_frame(image, clip.rotation)
            if play:
                self._still_clock = (_time.monotonic(), t)
                self._still_timer.start()
            return

        # A proxy is a full-length re-encode of the same source (never trimmed), so the
        # timeline <-> source-time mapping below is identical whichever file actually
        # gets opened -- only the preview's decoding gets lighter.
        playback_source = self._resolve_source(clip.source)
        if not os.path.isfile(playback_source):
            self._fail(f"File not found: {os.path.basename(playback_source)}", quiet=not play)
            return
        if not HAVE_MULTIMEDIA:
            self._fail("Video playback needs Qt Multimedia, which is not available.",
                       quiet=not play)
            return
        self._pending = (int(segment.source_time(t) * 1000), play)
        if self._loaded_source != playback_source:
            self._loaded_source = playback_source
            self._status_ready = False
            self._player.setSource(QUrl.fromLocalFile(playback_source))
        elif self._status_ready:
            self._apply_pending()

    def _apply_pending(self) -> None:
        if self._pending is None:
            return
        target_ms, play = self._pending
        self._pending = None
        segment = self.current_segment
        if segment is None:
            return
        self._player.setPlaybackRate(segment.speed)
        self._audio.setVolume(min(1.0, segment.clip.volume))
        self._settling = True
        self._settle_target = target_ms
        self._player.setPosition(target_ms)
        if play:
            self._player.play()
        else:
            self._player.pause()

    # ---- photos ---------------------------------------------------------------
    def _still(self, path: str) -> Optional[QImage]:
        image = self._stills.get(path)
        if image is None:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            image = reader.read()
            if image.isNull():
                return None
            if image.height() > 1080:
                image = image.scaledToHeight(1080, Qt.TransformationMode.SmoothTransformation)
            if len(self._stills) >= _MAX_STILLS:
                self._stills.pop(next(iter(self._stills)))
            self._stills[path] = image
        return image

    def _tick_still(self, now: Optional[float] = None) -> None:
        segment = self.current_segment
        if segment is None or segment.clip.kind not in STATIC_KINDS or not self._playing:
            self._still_timer.stop()
            return
        started, base = self._still_clock
        t = base + ((now if now is not None else _time.monotonic()) - started)
        if t >= segment.end - 1e-6:
            self._advance()
        else:
            self._time = t
            self.timeChanged.emit(t)

    # ---- video callbacks --------------------------------------------------------
    def _on_frame(self, frame) -> None:
        segment = self.current_segment
        if segment is None or segment.clip.kind in STATIC_KINDS or not frame.isValid():
            return
        image = frame.toImage()
        if not image.isNull():
            self._emit_frame(image, segment.clip.rotation)

    def _on_position(self, ms: int) -> None:
        if self._settling:
            if abs(ms - self._settle_target) < 700:
                self._settling = False
            else:
                return
        segment = self.current_segment
        if segment is None or segment.clip.kind in STATIC_KINDS:
            return
        source = ms / 1000.0
        self._time = min(max(segment.timeline_time(source), segment.start), segment.end)
        self.timeChanged.emit(self._time)
        if self._playing and source >= segment.src_end - 0.03:
            self._advance()

    def _on_status(self, status) -> None:
        loaded = (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia)
        if status in loaded:
            self._status_ready = True
            self._apply_pending()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia and self._playing:
            self._advance()

    def _on_error(self, _error, message: str = "") -> None:
        self._fail(message or "The video could not be played.")

    # ---- moving on ----------------------------------------------------------------
    def _advance(self) -> None:
        nxt = self._index + 1
        if nxt < len(self._segments):
            self._load(nxt, self._segments[nxt].start, play=True)
        else:
            self._finish()

    def _finish(self) -> None:
        self._still_timer.stop()
        if HAVE_MULTIMEDIA and self._loaded_source is not None:
            self._player.pause()
        self._time = self.duration
        self._set_playing(False)
        self.timeChanged.emit(self._time)

    def _fail(self, message: str, quiet: bool = False) -> None:
        """Stop playing. ``quiet`` skips the message (e.g. just showing a frame while paused)."""
        self._still_timer.stop()
        self._set_playing(False)
        if not quiet:
            self.failed.emit(message)

    def _emit_frame(self, image: QImage, rotation: int) -> None:
        if rotation % 360:
            image = image.transformed(QTransform().rotate(rotation))
        self.has_frame = True
        self.frameReady.emit(image)
