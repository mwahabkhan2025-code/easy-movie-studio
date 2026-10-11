"""Compress/Convert a video and Extract audio from a file -- both work on any file
the person picks from disk, independent of the current project's storyboard.

Both dialogs share the same run-with-progress machinery as SaveMovieDialog (a plan is
built, then run on a background QThread with a cancellable progress bar); they are
reusing it rather than importing it directly because each needs its own file-picking
flow, not a project to export.
"""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QLabel, QLineEdit, QMessageBox, QProgressDialog, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)

from .. import APP_NAME
from ..engine.export import ExportHandle, ExportRunError, run_export
from ..engine.export_plan import ExportError
from ..engine.file_tools import COMPRESS_PRESETS, build_compress_plan, build_extract_audio_plan
from ..engine.probe import ProbeError, probe
from ..engine.properties import format_size

_SPEED_PRESETS = ["ultrafast", "veryfast", "fast", "medium", "slow", "veryslow"]
_AUDIO_BITRATES = ["96k", "128k", "192k", "256k", "320k"]
MEDIA_FILTER = ("Media files (*.mp4 *.mov *.mkv *.avi *.wmv *.webm *.m4v *.mpg *.mpeg *.mp3 "
               "*.wav *.m4a *.aac *.flac *.ogg);;All files (*)")


class _PlanWorker(QObject):
    progress = Signal(float)
    finished = Signal()
    failed = Signal(str, str)

    def __init__(self, plan) -> None:
        super().__init__()
        self.plan = plan
        self.handle: Optional[ExportHandle] = None

    def run(self) -> None:
        try:
            run_export(self.plan, on_progress=self.progress.emit, on_handle=self._store_handle)
        except ExportRunError as exc:
            self.failed.emit(str(exc), exc.log_tail)
            return
        self.finished.emit()

    def _store_handle(self, handle: ExportHandle) -> None:
        self.handle = handle

    def cancel(self) -> None:
        if self.handle is not None:
            self.handle.cancel()


def _run_plan_with_progress(parent: QWidget, plan, output_path: str, title: str) -> None:
    progress = QProgressDialog(title, "Cancel", 0, 100, parent)
    progress.setWindowTitle(title)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    progress.setValue(0)

    thread = QThread(parent)
    worker = _PlanWorker(plan)
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
        QMessageBox.information(parent, APP_NAME, f"Saved to:\n{output_path}")

    def on_failed(message: str, log_tail: str) -> None:
        cleanup()
        progress.close()
        if "cancelled" in message.lower():
            return
        detail = f"\n\n{log_tail}" if log_tail else ""
        QMessageBox.critical(parent, APP_NAME, f"{message}{detail}")

    worker.finished.connect(on_finished)
    worker.failed.connect(on_failed)
    # Kept on the parent dialog so Python doesn't garbage-collect the thread/worker
    # mid-run; the attribute names are unique per dialog instance.
    parent._tool_thread, parent._tool_worker = thread, worker
    thread.start()


class CompressVideoDialog(QDialog):
    """Compress or convert a single video file to a new file, reusing the export
    presets (resolution/quality ladder) from the Save Movie dialog."""

    def __init__(self, default_dir: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Compress / Convert video")
        self.setMinimumWidth(420)
        self.default_dir = default_dir
        self.input_path = ""

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.input_row = QLineEdit()
        self.input_row.setReadOnly(True)
        pick_input = QPushButton("Choose file...")
        pick_input.clicked.connect(self._choose_input)
        input_box = QVBoxLayout()
        input_box.addWidget(self.input_row)
        input_box.addWidget(pick_input)
        form.addRow("Video to compress:", input_box)

        self.preset_box = QComboBox()
        for preset_id, preset in COMPRESS_PRESETS.items():
            self.preset_box.addItem(preset.label, preset_id)
        self.preset_box.currentIndexChanged.connect(self._update_from_preset)
        form.addRow("Preset:", self.preset_box)

        self.quality_box = QSpinBox()
        self.quality_box.setRange(1, 51)
        self.quality_box.setToolTip("Lower is higher quality and a larger file (FFmpeg CRF).")
        form.addRow("Quality (CRF):", self.quality_box)

        self.speed_box = QComboBox()
        self.speed_box.addItems(_SPEED_PRESETS)
        self.speed_box.setToolTip("Slower encoding gives a smaller file at the same quality.")
        form.addRow("Encoding speed:", self.speed_box)

        self.info_label = QLabel("Choose a file to see its details.")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color:#68737f;")
        layout.addLayout(form)
        layout.addWidget(self.info_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.run_button = QPushButton("Compress...")
        self.run_button.setDefault(True)
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self._choose_output_and_run)
        buttons.addButton(self.run_button, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_from_preset()

    def _choose_input(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a video", self.default_dir,
                                              MEDIA_FILTER)
        if not path:
            return
        try:
            info = probe(path)
        except ProbeError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return
        if info.video is None:
            QMessageBox.critical(self, APP_NAME,
                                 "That file has no video stream to compress.")
            return
        self.input_path = path
        self._info = info
        self.input_row.setText(path)
        w, h = info.video.display_size
        size_text = format_size(info.size_bytes) if info.size_bytes else "unknown size"
        self.info_label.setText(f"{w}x{h}, {info.duration or 0:.1f}s, {size_text}")
        self.run_button.setEnabled(True)
        self._update_from_preset()

    def current_preset_id(self) -> str:
        return self.preset_box.currentData()

    def _update_from_preset(self) -> None:
        from ..engine.export_plan import PRESETS
        preset = PRESETS[self.current_preset_id()]
        self.quality_box.setValue(preset.crf)
        index = self.speed_box.findText(preset.speed_preset)
        if index >= 0:
            self.speed_box.setCurrentIndex(index)

    def _choose_output_and_run(self) -> None:
        if not self.input_path:
            return
        base = os.path.splitext(os.path.basename(self.input_path))[0] + "_compressed.mp4"
        suggested = os.path.join(self.default_dir or os.path.dirname(self.input_path), base)
        path, _ = QFileDialog.getSaveFileName(self, "Save compressed video", suggested,
                                              "MP4 (*.mp4);;MKV (*.mkv);;MOV (*.mov);;"
                                              "All files (*)")
        if not path:
            return
        try:
            plan = build_compress_plan(self.input_path, path, preset_id=self.current_preset_id(),
                                       crf=self.quality_box.value(),
                                       speed_preset=self.speed_box.currentText(),
                                       info=getattr(self, "_info", None))
        except (ExportError, ValueError) as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return
        _run_plan_with_progress(self, plan, path, "Compressing video...")
        self.accept()


class ExtractAudioDialog(QDialog):
    """Pull the audio out of a video file (or re-encode an audio file) into an MP3."""

    def __init__(self, default_dir: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Extract audio")
        self.setMinimumWidth(420)
        self.default_dir = default_dir
        self.input_path = ""

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.input_row = QLineEdit()
        self.input_row.setReadOnly(True)
        pick_input = QPushButton("Choose file...")
        pick_input.clicked.connect(self._choose_input)
        input_box = QVBoxLayout()
        input_box.addWidget(self.input_row)
        input_box.addWidget(pick_input)
        form.addRow("Video or audio file:", input_box)

        self.bitrate_box = QComboBox()
        self.bitrate_box.addItems(_AUDIO_BITRATES)
        self.bitrate_box.setCurrentText("192k")
        form.addRow("Audio bitrate:", self.bitrate_box)

        self.info_label = QLabel("Choose a file to see its details.")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color:#68737f;")
        layout.addLayout(form)
        layout.addWidget(self.info_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.run_button = QPushButton("Extract...")
        self.run_button.setDefault(True)
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self._choose_output_and_run)
        buttons.addButton(self.run_button, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _choose_input(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a file", self.default_dir,
                                              MEDIA_FILTER)
        if not path:
            return
        try:
            info = probe(path)
        except ProbeError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return
        if not info.has_audio:
            QMessageBox.critical(self, APP_NAME, "That file doesn't have an audio track.")
            return
        self.input_path = path
        self._info = info
        self.input_row.setText(path)
        size_text = format_size(info.size_bytes) if info.size_bytes else "unknown size"
        kind = "video" if info.video is not None else "audio"
        self.info_label.setText(f"{kind} file, {info.duration or 0:.1f}s, {size_text}")
        self.run_button.setEnabled(True)

    def _choose_output_and_run(self) -> None:
        if not self.input_path:
            return
        base = os.path.splitext(os.path.basename(self.input_path))[0] + ".mp3"
        suggested = os.path.join(self.default_dir or os.path.dirname(self.input_path), base)
        path, _ = QFileDialog.getSaveFileName(self, "Save extracted audio", suggested,
                                              "MP3 (*.mp3);;All files (*)")
        if not path:
            return
        try:
            plan = build_extract_audio_plan(self.input_path, path,
                                            audio_bitrate=self.bitrate_box.currentText(),
                                            info=getattr(self, "_info", None))
        except (ExportError, ValueError) as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return
        _run_plan_with_progress(self, plan, path, "Extracting audio...")
        self.accept()
