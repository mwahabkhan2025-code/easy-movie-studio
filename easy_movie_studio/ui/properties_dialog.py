"""Read-only Properties dialog for a clip's media file."""

from __future__ import annotations

import os
from typing import List, Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from ..engine.media_info import MediaInfo
from ..engine.properties import Section, compare_with_project, describe, sections_to_text
from ..model import Clip, ProjectSettings


class PropertiesDialog(QDialog):
    """Shows details from ``info`` (or an error message when it could not be read)."""

    def __init__(self, path: str, info: Optional[MediaInfo], clip: Optional[Clip],
                 settings: ProjectSettings, error: str = "",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.path = path
        self.setWindowTitle(f"Properties - {os.path.basename(path)}")
        self.setMinimumSize(460, 420)
        self.resize(500, 560)

        self.notes: List[str] = []
        self.sections: List[Section] = []
        if info is not None:
            self.sections = describe(info, clip)
            self.notes = compare_with_project(info, settings)

        layout = QVBoxLayout(self)
        if error or info is None:
            banner = QLabel(f"Media information isn't available.\n{error}".strip())
            banner.setWordWrap(True)
            banner.setStyleSheet("background:#fbe3e3; border:1px solid #e0a0a0; padding:6px;")
            layout.addWidget(banner)
        if self.notes:
            note = QLabel("\u26a0  " + "\n\u26a0  ".join(self.notes))
            note.setObjectName("warningBanner")
            note.setWordWrap(True)
            note.setStyleSheet("background:#fff6cc; border:1px solid #e2d27a; padding:6px;")
            layout.addWidget(note)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(4, 4, 4, 4)
        for title, rows in self.sections:
            heading = QLabel(f"<b>{title}</b>")
            heading.setStyleSheet("color:#2f7fc1; padding-top:6px;")
            body_layout.addWidget(heading)
            rule = QFrame()
            rule.setFrameShape(QFrame.Shape.HLine)
            rule.setStyleSheet("color:#d5d9de;")
            body_layout.addWidget(rule)
            grid = QGridLayout()
            grid.setColumnStretch(1, 1)
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(3)
            for r, (label, value) in enumerate(rows):
                name = QLabel(label)
                name.setStyleSheet("color:#68737f;")
                name.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
                text = QLabel(value)
                text.setWordWrap(True)
                text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                grid.addWidget(name, r, 0)
                grid.addWidget(text, r, 1)
            body_layout.addLayout(grid)
        body_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        self.copy_button = QPushButton("Copy details")
        self.copy_button.setEnabled(bool(self.sections))
        self.copy_button.clicked.connect(self.copy_details)
        self.folder_button = QPushButton("Open file location")
        self.folder_button.setEnabled(os.path.isdir(os.path.dirname(path)))
        self.folder_button.clicked.connect(self.open_location)
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.folder_button)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def details_text(self) -> str:
        return sections_to_text(self.sections, self.notes)

    def copy_details(self) -> None:
        QGuiApplication.clipboard().setText(self.details_text())

    def open_location(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.path)))
