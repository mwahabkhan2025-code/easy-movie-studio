"""Dialogs for Home > Title, Caption, and Credits."""

from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QGridLayout, QLineEdit, QPlainTextEdit, QPushButton,
                               QToolButton, QVBoxLayout, QWidget)

_BACKGROUNDS = ["Black", "White", "Dark blue", "Dark red", "Gray"]
_CREDIT_ROLE_HINTS = {
    "credits": "", "director": "Directed by", "cast": "Starring",
    "location": "Filmed on location at", "music": "Music by",
}


class TitleDialog(QDialog):
    def __init__(self, initial_text: str = "", initial_background: str = "Black",
                initial_duration: float = 5.0, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add a title")
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)

        self.text_edit = QPlainTextEdit(initial_text)
        self.text_edit.setPlaceholderText("Type your title here")
        self.text_edit.setMaximumHeight(100)
        layout.addWidget(self.text_edit)

        form = QFormLayout()
        self.background_box = QComboBox()
        self.background_box.addItems(_BACKGROUNDS)
        index = self.background_box.findText(initial_background, Qt.MatchFlag.MatchFixedString)
        if index >= 0:
            self.background_box.setCurrentIndex(index)
        form.addRow("Background:", self.background_box)

        self.duration_box = QDoubleSpinBox()
        self.duration_box.setRange(1.0, 30.0)
        self.duration_box.setSuffix(" s")
        self.duration_box.setValue(initial_duration)
        form.addRow("Duration:", self.duration_box)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.text_edit.setFocus()

    def values(self) -> Tuple[str, str, float]:
        return (self.text_edit.toPlainText(), self.background_box.currentText(),
               self.duration_box.value())


class CaptionDialog(QDialog):
    def __init__(self, initial_text: str = "", initial_position: str = "bottom",
                parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add a caption")
        self.setMinimumWidth(340)
        layout = QVBoxLayout(self)

        self.text_edit = QPlainTextEdit(initial_text)
        self.text_edit.setPlaceholderText("Type a caption for this clip")
        self.text_edit.setMaximumHeight(80)
        layout.addWidget(self.text_edit)

        form = QFormLayout()
        self.position_box = QComboBox()
        self.position_box.addItem("Top", "top")
        self.position_box.addItem("Middle", "middle")
        self.position_box.addItem("Bottom", "bottom")
        index = self.position_box.findData(initial_position)
        if index >= 0:
            self.position_box.setCurrentIndex(index)
        form.addRow("Position:", self.position_box)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.text_edit.setFocus()

    def values(self) -> Tuple[str, str]:
        return self.text_edit.toPlainText(), self.position_box.currentData()


class CreditsDialog(QDialog):
    def __init__(self, role_hint: str = "", initial_background: str = "Black",
                initial_duration: float = 6.0, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add credits")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)

        self._rows: List[Tuple[QLineEdit, QLineEdit]] = []
        self.grid_holder = QWidget()
        self.grid = QGridLayout(self.grid_holder)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 2)
        layout.addWidget(self.grid_holder)
        self._add_row(role_hint, "")

        add_row_button = QPushButton("+ Add another line")
        add_row_button.clicked.connect(lambda: self._add_row("", ""))
        layout.addWidget(add_row_button)

        form = QFormLayout()
        self.background_box = QComboBox()
        self.background_box.addItems(_BACKGROUNDS)
        index = self.background_box.findText(initial_background, Qt.MatchFlag.MatchFixedString)
        if index >= 0:
            self.background_box.setCurrentIndex(index)
        form.addRow("Background:", self.background_box)

        self.duration_box = QDoubleSpinBox()
        self.duration_box.setRange(1.0, 60.0)
        self.duration_box.setSuffix(" s")
        self.duration_box.setValue(initial_duration)
        form.addRow("Duration:", self.duration_box)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_row(self, role: str, name: str) -> None:
        row = len(self._rows)
        role_edit = QLineEdit(role)
        role_edit.setPlaceholderText("Role (e.g. Directed by)")
        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText("Name")
        self.grid.addWidget(role_edit, row, 0)
        self.grid.addWidget(name_edit, row, 1)
        remove = QToolButton()
        remove.setText("\u2715")
        remove.setToolTip("Remove this line")
        remove.clicked.connect(lambda: self._remove_row(role_edit, name_edit, remove))
        self.grid.addWidget(remove, row, 2)
        self._rows.append((role_edit, name_edit))
        if row == 0:
            role_edit.setFocus()

    def _remove_row(self, role_edit: QLineEdit, name_edit: QLineEdit,
                    button: QToolButton) -> None:
        if len(self._rows) <= 1:
            return  # always keep at least one line
        self._rows = [r for r in self._rows if r[0] is not role_edit]
        for widget in (role_edit, name_edit, button):
            self.grid.removeWidget(widget)
            widget.deleteLater()

    def values(self) -> Tuple[List[List[str]], str, float]:
        lines = [[role.text(), name.text()] for role, name in self._rows
                if role.text().strip() or name.text().strip()]
        return lines, self.background_box.currentText(), self.duration_box.value()
