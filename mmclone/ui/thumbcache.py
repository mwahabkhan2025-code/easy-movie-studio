"""Thumbnail cache: asks workers for frames and hands out QImages when they arrive."""

from __future__ import annotations

from collections import OrderedDict
from typing import Dict, Optional, Set, Tuple

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QImage, QTransform

from ..engine.thumbnails import extract_frame_png
from .workers import TaskManager

Key = Tuple[str, float, int]  # path, time (rounded), pixel height
_MAX_ENTRIES = 600


class ThumbnailCache(QObject):
    """``ready`` fires (coalesced) whenever new thumbnails have arrived."""

    ready = Signal()

    def __init__(self, tasks: TaskManager, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._tasks = tasks
        self._images: "OrderedDict[Key, Optional[QImage]]" = OrderedDict()
        self._rotated: Dict[Tuple[Key, int], QImage] = {}
        self._pending: Set[Key] = set()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self.ready.emit)

    @staticmethod
    def _key(path: str, time: Optional[float], height: int) -> Key:
        return (path, round(time, 1) if time is not None else -1.0, int(height))

    def get(self, path: str, time: Optional[float], height: int,
            rotation: int = 0) -> Optional[QImage]:
        """The thumbnail if it is ready, else None (and it is requested)."""
        key = self._key(path, time, height)
        if key in self._images:
            image = self._images[key]
            if image is None:
                return None  # known failure: do not retry
            self._images.move_to_end(key)
            if rotation % 360:
                cached = self._rotated.get((key, rotation))
                if cached is None:
                    cached = image.transformed(QTransform().rotate(rotation))
                    self._rotated[(key, rotation)] = cached
                return cached
            return image
        self._request(key, path, time, height)
        return None

    def _request(self, key: Key, path: str, time: Optional[float], height: int) -> None:
        if key in self._pending:
            return
        self._pending.add(key)
        self._tasks.submit(extract_frame_png, path, time if time is not None else None, height,
                           on_done=lambda data, k=key: self._store(k, data),
                           on_failed=lambda _msg, k=key: self._store(k, None))

    def _store(self, key: Key, data: Optional[bytes]) -> None:
        self._pending.discard(key)
        image = QImage.fromData(data, "PNG") if data else None
        self._images[key] = image if image is not None and not image.isNull() else None
        while len(self._images) > _MAX_ENTRIES:
            old_key, _ = self._images.popitem(last=False)
            for rk in [k for k in self._rotated if k[0] == old_key]:
                del self._rotated[rk]
        if not self._timer.isActive():
            self._timer.start()

    def clear(self) -> None:
        self._images.clear()
        self._rotated.clear()
