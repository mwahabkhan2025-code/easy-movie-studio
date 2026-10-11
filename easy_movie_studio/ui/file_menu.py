"""The File menu panel (menu on the left, recent projects on the right)."""

from __future__ import annotations

import os
from functools import partial
from typing import Optional, Sequence

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout,
                               QWidget)

from .icons import icon
from .ribbon_spec import GalleryItem

_ROWS = (
    ("file.new_project", "New project", "mdi6.file-plus-outline", False),
    ("file.open_project", "Open project", "mdi6.folder-open-outline", False),
    ("file.save_project", "Save project", "mdi6.content-save-outline", False),
    ("file.save_project_as", "Save project as", "mdi6.content-save-edit-outline", False),
    None,
    ("file.save_movie", "Save movie  \u25b8", "mdi6.movie-open-check-outline", True),
    None,
    ("file.compress_video", "Compress / Convert video", "mdi6.file-video-outline", False),
    ("file.extract_audio", "Extract audio", "mdi6.music-note-outline", False),
    None,
    ("file.options", "Options", "mdi6.cog-outline", False),
    ("file.about", "About", "mdi6.information-outline", False),
    None,
    ("file.exit", "Exit", "mdi6.exit-to-app", False),
)


class FileMenuPanel(QFrame):
    commandTriggered = Signal(str)

    def __init__(self, presets: Sequence[GalleryItem], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self._presets = list(presets)
        self.setObjectName("fileMenu")
        self.setFixedSize(540, 400)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        left = QFrame()
        left.setObjectName("fileMenuLeft")
        left.setFixedWidth(230)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 6, 0, 6)
        left_layout.setSpacing(0)
        for row in _ROWS:
            if row is None:
                sep = QFrame()
                sep.setObjectName("fileSep")
                left_layout.addWidget(sep)
                continue
            command, text, icon_name, has_submenu = row
            button = QPushButton(text)
            button.setObjectName("fileRow")
            button.setIcon(icon(icon_name))
            button.setIconSize(QSize(20, 20))
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(partial(self._row_clicked, command, button, has_submenu))
            left_layout.addWidget(button)
        left_layout.addStretch(1)

        right = QFrame()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        title = QLabel("Recent projects")
        title.setObjectName("recentTitle")
        right_layout.addWidget(title)
        self._recent_box = QVBoxLayout()
        self._recent_box.setSpacing(0)
        right_layout.addLayout(self._recent_box)
        right_layout.addStretch(1)

        root.addWidget(left)
        root.addWidget(right, 1)

    def _row_clicked(self, command: str, button: QPushButton, has_submenu: bool,
                     _checked: bool = False) -> None:
        anchor = button.mapToGlobal(QPoint(button.width(), 0))
        self.hide()
        if not has_submenu:
            self.commandTriggered.emit(command)
            return
        menu = QMenu()
        for preset in self._presets:
            action = menu.addAction(preset.text)
            action.setData(preset.id)
        chosen = menu.exec(anchor)
        if chosen is not None:
            self.commandTriggered.emit(f"{command}/{chosen.data()}")

    def _recent_clicked(self, path: str, _checked: bool = False) -> None:
        self.hide()
        self.commandTriggered.emit(f"file.open_recent:{path}")

    def set_recent(self, paths: Sequence[str]) -> None:
        while self._recent_box.count():
            item = self._recent_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for path in paths:
            button = QPushButton(os.path.basename(path))
            button.setObjectName("recentRow")
            button.setToolTip(path)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(partial(self._recent_clicked, path))
            self._recent_box.addWidget(button)

    def show_at(self, global_pos: QPoint) -> None:
        self.move(global_pos)
        self.show()
