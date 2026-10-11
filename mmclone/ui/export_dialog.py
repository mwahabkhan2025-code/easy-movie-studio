"""Save movie dialog: pick a preset (or customize it), see an estimated size,
then run the export with a progress bar the person can cancel."""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QLabel, QMessageBox, QProgressDialog, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from .. import APP_NAME
from ..engine.export import ExportHandle, ExportRunError, run_export
from ..engine.export_plan import (PRESETS, ExportSettings, build_export_plan,
                                  estimate_output_bytes, resolve_settings)
from ..engine.properties import format_size
from ..model import Project

_CONTAINER_EXT = {"video": ".mp4", "audio": ".mp3", "gif": ".gif"}
_SPEED_PRESETS = ["ultrafast", "veryfast", "fast", "medium", "slow", "veryslow"]


class _ExportWorker(QObject):
    progress = Signal(float)
    finished = Signal()
    failed = Signal(str, str)  # message, log tail

    def __init__(self, plan) -> None:
        super().__init__()
        self.plan = plan
        self.handle: Optional[ExportHandle] = None

    def run(self) -> None:
        try:
            run_export(self.plan, on_progress=self.progress.emit,
                      on_handle=self._store_handle)
        except ExportRunError as exc:
            self.failed.emit(str(exc), exc.log_tail)
            return
        self.finished.emit()

    def _store_handle(self, handle: ExportHandle) -> None:
        self.handle = handle

    def cancel(self) -> None:
        if self.handle is not None:
            self.handle.cancel()


class SaveMovieDialog(QDialog):
    def __init__(self, project: Project, silent_sources: set, default_dir: str = "",
                default_preset: str = "recommended", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.project = project
        self.silent_sources = silent_sources
        self.default_dir = default_dir
        self.setWindowTitle("Save movie")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.preset_box = QComboBox()
        for preset_id, preset in PRESETS.items():
            self.preset_box.addItem(preset.label, preset_id)
        index = self.preset_box.findData(default_preset)
        if index >= 0:
            self.preset_box.setCurrentIndex(index)
        self.preset_box.currentIndexChanged.connect(self._update_from_preset)
        form.addRow("Preset:", self.preset_box)

        self.quality_box = QSpinBox()
        self.quality_box.setRange(1, 51)
        self.quality_box.setToolTip("Lower is higher quality and a larger file (FFmpeg CRF).")
        self.quality_box.valueChanged.connect(self._update_estimate)
        form.addRow("Quality (CRF):", self.quality_box)

        self.speed_box = QComboBox()
        self.speed_box.addItems(_SPEED_PRESETS)
        self.speed_box.setToolTip("Slower encoding gives a smaller file at the same quality.")
        form.addRow("Encoding speed:", self.speed_box)

        self.size_label = QLabel()
        form.addRow("Estimated size:", self.size_label)
        layout.addLayout(form)

        note = QLabel("The estimate is approximate -- actual size depends on the footage.")
        note.setStyleSheet("color:#68737f;")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.save_button = QPushButton("Save movie...")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._choose_path_and_run)
        buttons.addButton(self.save_button, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_from_preset()

    # ---- preset / estimate --------------------------------------------------
    def current_preset_id(self) -> str:
        return self.preset_box.currentData()

    def _update_from_preset(self) -> None:
        settings = resolve_settings(self.project, self.current_preset_id())
        is_video = settings.output_kind == "video"
        self.quality_box.setEnabled(is_video)
        self.speed_box.setEnabled(is_video)
        self.quality_box.setValue(settings.crf)
        speed_index = self.speed_box.findText(settings.speed_preset)
        if speed_index >= 0:
            self.speed_box.setCurrentIndex(speed_index)
        self._update_estimate()

    def _current_settings(self) -> ExportSettings:
        settings = resolve_settings(self.project, self.current_preset_id())
        settings.crf = self.quality_box.value()
        settings.speed_preset = self.speed_box.currentText()
        return settings

    def _update_estimate(self) -> None:
        settings = self._current_settings()
        size = estimate_output_bytes(self.project.duration, settings)
        self.size_label.setText(f"about {format_size(size)}")

    # ---- running the export ---------------------------------------------------
    def _choose_path_and_run(self) -> None:
        settings = self._current_settings()
        ext = _CONTAINER_EXT[settings.output_kind]
        suggested = os.path.join(self.default_dir or "", (self.project.name or "My Movie") + ext)
        path, _ = QFileDialog.getSaveFileName(self, "Save movie", suggested, f"*{ext}")
        if not path:
            return
        if not path.lower().endswith(ext):
            path += ext
        try:
            plan = build_export_plan(self.project, path, settings, self.silent_sources)
        except Exception as exc:  # ExportError or a bad project state
            QMessageBox.critical(self, APP_NAME, str(exc))
            return
        self._run_with_progress(plan, path)

    def _run_with_progress(self, plan, path: str) -> None:
        progress = QProgressDialog("Saving movie...", "Cancel", 0, 100, self)
        progress.setWindowTitle("Save movie")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)

        thread = QThread(self)
        worker = _ExportWorker(plan)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(lambda f: progress.setValue(int(f * 100)))
        progress.canceled.connect(worker.cancel)

        def cleanup() -> None:
            thread.quit()
            thread.wait(3000)

        def on_finished() -> None:
            cleanup()
            progress.close()
            self.accept()
            QMessageBox.information(self, APP_NAME, f"Movie saved to:\n{path}")

        def on_failed(message: str, log_tail: str) -> None:
            cleanup()
            progress.close()
            if "cancelled" in message.lower():
                return
            detail = f"\n\n{log_tail}" if log_tail else ""
            QMessageBox.critical(self, APP_NAME, f"{message}{detail}")

        worker.finished.connect(on_finished)
        worker.failed.connect(on_failed)
        self._thread, self._worker = thread, worker  # keep references alive
        thread.start()
