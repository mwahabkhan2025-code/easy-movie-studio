"""Right-click > Picture-in-picture position... on an overlay-track clip."""

from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                               QSlider, QVBoxLayout, QWidget)


class _PercentSlider(QWidget):
    def __init__(self, minimum: int, maximum: int, value: int) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setValue(value)
        self.label = QLabel(f"{value}%")
        self.label.setFixedWidth(40)
        self.slider.valueChanged.connect(lambda v: self.label.setText(f"{v}%"))
        layout.addWidget(self.slider)
        layout.addWidget(self.label)

    def value(self) -> float:
        return self.slider.value() / 100.0


class OverlayPositionDialog(QDialog):
    def __init__(self, x: float = 0.75, y: float = 0.75, scale: float = 0.35,
                opacity: float = 1.0, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Picture-in-picture position")
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.x_row = _PercentSlider(0, 100, round(x * 100))
        form.addRow("Horizontal position:", self.x_row)
        self.y_row = _PercentSlider(0, 100, round(y * 100))
        form.addRow("Vertical position:", self.y_row)
        self.scale_row = _PercentSlider(5, 100, round(scale * 100))
        form.addRow("Size:", self.scale_row)
        self.opacity_row = _PercentSlider(0, 100, round(opacity * 100))
        form.addRow("Opacity:", self.opacity_row)
        layout.addLayout(form)

        note = QLabel("Position is where the overlay is centered, as a percentage of the "
                      "frame -- 50% / 50% is the middle.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#68737f;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> Tuple[float, float, float, float]:
        return (self.x_row.value(), self.y_row.value(), self.scale_row.value(),
               self.opacity_row.value())
