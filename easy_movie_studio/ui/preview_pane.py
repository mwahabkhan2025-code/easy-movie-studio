"""Left-hand preview: video surface, time readout, seek slider, transport buttons."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QKeyEvent, QPainter
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QSizePolicy, QSlider, QToolButton,
                               QVBoxLayout, QWidget)

from ..util import format_time
from .icons import icon


class VideoSurface(QWidget):
    """Black rectangle that keeps the project's aspect ratio (video goes here later)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._aspect = (16, 9)
        self._image: Optional[QImage] = None
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def set_aspect(self, width: int, height: int) -> None:
        self._aspect = (max(1, width), max(1, height))
        self.updateGeometry()
        self.update()

    def set_image(self, image: Optional[QImage]) -> None:
        self._image = image
        self.update()

    def current_image(self) -> Optional[QImage]:
        return self._image

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return int(width * self._aspect[1] / self._aspect[0])

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(460, self.heightForWidth(460))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(240, self.heightForWidth(240))

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        if self._image is not None and not self._image.isNull():
            # fit inside the frame, keeping the picture's own shape (black bars like export)
            scale = min(self.width() / self._image.width(), self.height() / self._image.height())
            w, h = self._image.width() * scale, self._image.height() * scale
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h),
                              self._image)
        painter.end()


class FullscreenPreview(QWidget):
    """Full-screen view of the preview. Esc closes; Space or a click plays/pauses."""

    toggleRequested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Preview")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._image: Optional[QImage] = None
        try:
            from .icons import app_icon
            self.setWindowIcon(app_icon())
        except Exception:
            pass

    def set_image(self, image: Optional[QImage]) -> None:
        self._image = image
        if self.isVisible():
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        if self._image is not None and not self._image.isNull():
            scale = min(self.width() / self._image.width(), self.height() / self._image.height())
            w, h = self._image.width() * scale, self._image.height() * scale
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h),
                              self._image)
        painter.end()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() == Qt.Key.Key_Space:
            self.toggleRequested.emit()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.toggleRequested.emit()


class PreviewPane(QWidget):
    fullscreenRequested = Signal()
    transportPressed = Signal(str)  # "prev", "play", "next"
    seekRequested = Signal(float)   # fraction 0..1 of the movie, from the slider

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 10)
        layout.setSpacing(6)

        self.surface = VideoSurface()
        layout.addWidget(self.surface)

        clock_row = QHBoxLayout()
        clock_row.addStretch(1)
        self.time_label = QLabel(f"{format_time(0)}/{format_time(0)}")
        self.time_label.setObjectName("timeLabel")
        clock_row.addWidget(self.time_label)
        self.full_button = QToolButton()
        self.full_button.setObjectName("previewFull")
        self.full_button.setIcon(icon("mdi6.arrow-expand-all"))
        self.full_button.setToolTip("Preview full screen")
        self.full_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.full_button.clicked.connect(lambda: self.fullscreenRequested.emit())
        clock_row.addWidget(self.full_button)
        layout.addLayout(clock_row)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setEnabled(False)
        self._updating = False
        self.slider.valueChanged.connect(self._slider_changed)
        layout.addWidget(self.slider)

        transport = QHBoxLayout()
        transport.setSpacing(0)
        transport.addStretch(1)
        self.buttons = {}
        for key, name, icon_name in (("prev", "transportLeft", "mdi6.skip-previous"),
                                     ("play", "transportMid", "mdi6.play"),
                                     ("next", "transportRight", "mdi6.skip-next")):
            button = QToolButton()
            button.setObjectName(name)
            button.setIcon(icon(icon_name))
            button.setIconSize(QSize(18, 18))
            button.setEnabled(False)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setToolTip({"prev": "Previous frame", "play": "Play",
                               "next": "Next frame"}[key])
            button.clicked.connect(lambda _c=False, k=key: self.transportPressed.emit(k))
            transport.addWidget(button)
            self.buttons[key] = button
        transport.addStretch(1)
        layout.addLayout(transport)
        layout.addStretch(1)

    def set_aspect(self, width: int, height: int) -> None:
        self.surface.set_aspect(width, height)

    def _slider_changed(self, value: int) -> None:
        if not self._updating:
            self.seekRequested.emit(value / self.slider.maximum())

    def set_time(self, position: float, total: float) -> None:
        self.time_label.setText(f"{format_time(position)}/{format_time(total)}")
        self._updating = True
        try:
            fraction = position / total if total > 0 else 0.0
            self.slider.setValue(int(round(max(0.0, min(1.0, fraction)) * self.slider.maximum())))
        finally:
            self._updating = False

    def set_playing(self, playing: bool) -> None:
        self.buttons["play"].setIcon(icon("mdi6.pause" if playing else "mdi6.play"))
        self.buttons["play"].setToolTip("Pause" if playing else "Play")

    def set_poster(self, image: Optional[QImage]) -> None:
        self.surface.set_image(image)

    def set_playable(self, playable: bool) -> None:
        self.slider.setEnabled(playable)
        for button in self.buttons.values():
            button.setEnabled(playable)
