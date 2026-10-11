"""Project > Audio mix dialog."""

from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QLabel, QSlider, QVBoxLayout, QWidget)


def _percent_label(value: int) -> str:
    return f"{value}%"


class _VolumeRow(QWidget):
    def __init__(self, initial_percent: int) -> None:
        super().__init__()
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 200)
        self.slider.setValue(initial_percent)
        self.value_label = QLabel(_percent_label(initial_percent))
        self.value_label.setFixedWidth(42)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self.slider)
        row_layout.addWidget(self.value_label)
        self.slider.valueChanged.connect(lambda v: self.value_label.setText(_percent_label(v)))
        layout.addRow(row)

    def value(self) -> float:
        return self.slider.value() / 100.0


class AudioMixDialog(QDialog):
    def __init__(self, music_volume: float = 1.0, video_volume: float = 1.0,
                duck_music: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Audio mix")
        self.setMinimumWidth(340)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.video_row = _VolumeRow(round(video_volume * 100))
        form.addRow("Video volume:", self.video_row)
        self.music_row = _VolumeRow(round(music_volume * 100))
        form.addRow("Music volume:", self.music_row)
        layout.addLayout(form)

        self.duck_box = QCheckBox("Lower music volume where the video has its own sound")
        self.duck_box.setChecked(duck_music)
        self.duck_box.setToolTip("Applies a flat reduction to the whole music track -- it "
                                 "isn't synced moment-to-moment to when speech happens.")
        layout.addWidget(self.duck_box)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> Tuple[float, float, bool]:
        return self.music_row.value(), self.video_row.value(), self.duck_box.isChecked()
