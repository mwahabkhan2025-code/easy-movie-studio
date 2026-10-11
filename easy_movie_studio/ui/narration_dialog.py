"""Home > Record narration dialog.

Real microphone capture needs hardware this project's test environment does
not have, so this dialog is written to degrade clearly: if NarrationRecorder
reports recording isn't available, the dialog opens straight into a disabled,
explained state rather than letting the person click Record and hit a buried
error.
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from ..engine.narration import NarrationRecorder, RecordingError
from ..util import format_time


class NarrationDialog(QDialog):
    recorded = Signal(str, float)  # file path, duration in seconds

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Record narration")
        self.setMinimumWidth(320)
        self.recorder = NarrationRecorder()
        self._path: Optional[str] = None
        self._result: Optional[tuple] = None

        layout = QVBoxLayout(self)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.time_label = QLabel(format_time(0))
        self.time_label.setStyleSheet("font-size: 20pt;")
        layout.addWidget(self.time_label)

        buttons_row = QHBoxLayout()
        self.record_button = QPushButton("\u25cf Record")
        self.stop_button = QPushButton("\u25a0 Stop")
        self.stop_button.setEnabled(False)
        self.record_button.clicked.connect(self._start)
        self.stop_button.clicked.connect(self._stop)
        buttons_row.addWidget(self.record_button)
        buttons_row.addWidget(self.stop_button)
        layout.addLayout(buttons_row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                        | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self._cancel_and_close)
        layout.addWidget(self.buttons)

        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._tick)

        if self.recorder.available():
            self.status_label.setText("Ready to record from your default microphone.")
        else:
            self.status_label.setText(
                "No microphone is available (or the 'sounddevice'/'soundfile' packages "
                "aren't installed). Narration recording can't run on this machine.")
            self.record_button.setEnabled(False)

    def _start(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="narration_")
        os.close(fd)
        self._path = path
        try:
            self.recorder.start(path)
        except RecordingError as exc:
            self.status_label.setText(str(exc))
            return
        self.record_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("Recording...")
        self._timer.start()

    def _tick(self) -> None:
        self.time_label.setText(format_time(self.recorder.elapsed))

    def _stop(self) -> None:
        duration = self.recorder.stop()
        self._timer.stop()
        self.stop_button.setEnabled(False)
        if duration < 0.3:
            self.status_label.setText("That recording was too short -- try again.")
            self.record_button.setEnabled(True)
            self._cleanup_file()
            return
        self._result = (self._path, duration)
        self.status_label.setText(f"Recorded {format_time(duration)}. Click Save to add it, "
                                  "or Record again to replace it.")
        self.record_button.setEnabled(True)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(True)

    def _cleanup_file(self) -> None:
        if self._path and os.path.isfile(self._path):
            try:
                os.remove(self._path)
            except OSError:
                pass
        self._path = None

    def _cancel_and_close(self) -> None:
        self.recorder.cancel(self._path or "")
        if self._result is None:
            self._cleanup_file()
        self.reject()

    def result_values(self) -> Optional[tuple]:
        """(path, duration) if something was recorded and Save was clicked, else None."""
        return self._result
