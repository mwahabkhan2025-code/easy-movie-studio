"""File menu > Options: app-wide preferences (not stored with any one project)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout,
                               QWidget)

from ..engine.export_plan import PRESETS
from ..settings import AppSettings


class _PathRow(QWidget):
    """A read-only line edit plus a "Browse..." button for picking a folder."""

    def __init__(self, initial: str, placeholder: str) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit(initial)
        self.edit.setPlaceholderText(placeholder)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        layout.addWidget(self.edit)
        layout.addWidget(browse)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose a folder", self.edit.text())
        if path:
            self.edit.setText(path)

    def text(self) -> str:
        return self.edit.text().strip()


class OptionsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Options")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.preset_box = QComboBox()
        for preset_id, preset in PRESETS.items():
            self.preset_box.addItem(preset.label, preset_id)
        index = self.preset_box.findData(settings.default_export_preset)
        if index >= 0:
            self.preset_box.setCurrentIndex(index)
        form.addRow("Default export preset:", self.preset_box)

        self.project_dir_row = _PathRow(settings.default_project_dir,
                                        "(use whatever folder was opened last)")
        form.addRow("Default project folder:", self.project_dir_row)

        self.ffmpeg_dir_row = _PathRow(settings.ffmpeg_dir,
                                       "(search PATH, then the bundled FFmpeg)")
        form.addRow("FFmpeg folder:", self.ffmpeg_dir_row)
        ffmpeg_note = QLabel("Only needed to point at a specific FFmpeg build -- "
                             "most people can leave this blank.")
        ffmpeg_note.setStyleSheet("color:#68737f;")
        ffmpeg_note.setWordWrap(True)
        form.addRow("", ffmpeg_note)

        self.proxy_width_box = QSpinBox()
        self.proxy_width_box.setRange(160, 7680)
        self.proxy_width_box.setSingleStep(160)
        self.proxy_width_box.setValue(settings.proxy_min_width)
        self.proxy_width_box.setSuffix(" px")
        self.proxy_width_box.setToolTip("A video narrower than this already plays smoothly, "
                                        "so preview proxies skip it.")
        form.addRow("Make proxies for video wider than:", self.proxy_width_box)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> AppSettings:
        return AppSettings(default_export_preset=self.preset_box.currentData(),
                           default_project_dir=self.project_dir_row.text(),
                           ffmpeg_dir=self.ffmpeg_dir_row.text(),
                           proxy_min_width=self.proxy_width_box.value())
