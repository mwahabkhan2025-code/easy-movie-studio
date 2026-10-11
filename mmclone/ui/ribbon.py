"""Ribbon bar widgets, built from the declarative spec in ribbon_spec.py."""

from __future__ import annotations

import zlib
from functools import partial
from typing import Dict, List, Optional, Sequence

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPen,
                           QPixmap, QTextOption)
from PySide6.QtWidgets import (QButtonGroup, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel,
                               QMenu, QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from .icons import icon
from .ribbon_spec import (QUICK_ACCESS, Button, Gallery, Group, SmallColumn, Spin, Tab,
                          is_enabled)

BODY_HEIGHT = 98
_NO_FOCUS = Qt.FocusPolicy.NoFocus


def tile_pixmap(item_id: str, text: str, width: int, height: int) -> QPixmap:
    """Placeholder thumbnail for a gallery entry: tinted gradient with its name."""
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if item_id == "none":
        top, bottom = QColor("#ffffff"), QColor("#e2e8ee")
    else:
        hue = zlib.crc32(item_id.encode("utf-8")) % 360
        top, bottom = QColor.fromHsv(hue, 55, 250), QColor.fromHsv(hue, 120, 214)
    gradient = QLinearGradient(0, 0, 0, height)
    gradient.setColorAt(0, top)
    gradient.setColorAt(1, bottom)
    painter.fillRect(0, 0, width, height, QBrush(gradient))
    painter.setPen(QPen(QColor("#2d4a66")))
    font = QFont()
    font.setPointSizeF(7.5)
    painter.setFont(font)
    painter.drawText(QRectF(2, 2, width - 4, height - 4), text,
                     QTextOption(Qt.AlignmentFlag.AlignCenter))
    painter.end()
    return pixmap


class GalleryWidget(QWidget):
    """A row of selectable tiles with scroll-up / scroll-down / show-all arrows."""

    itemChosen = Signal(str, str)  # gallery id, item id

    def __init__(self, gallery: Gallery, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.gallery = gallery
        self._offset = 0
        self._current = gallery.items[0].id
        self._tiles: List[QToolButton] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        for _ in range(min(gallery.visible, len(gallery.items))):
            tile = QToolButton()
            tile.setObjectName("galleryTile")
            tile.setCheckable(True)
            tile.setFocusPolicy(_NO_FOCUS)
            tile.setFixedSize(gallery.tile_w, 50)
            tile.setIconSize(QSize(gallery.tile_w - 6, 44))
            tile.clicked.connect(partial(self._tile_clicked, tile))
            layout.addWidget(tile)
            self._tiles.append(tile)

        arrows = QVBoxLayout()
        arrows.setSpacing(0)
        arrows.setContentsMargins(0, 0, 0, 0)
        self._up = self._arrow("\u25b2")
        self._down = self._arrow("\u25bc")
        self._more = self._arrow("\u25be")
        self._up.clicked.connect(lambda: self._shift(-1))
        self._down.clicked.connect(lambda: self._shift(1))
        self._more.clicked.connect(self._show_all)
        for button in (self._up, self._down, self._more):
            arrows.addWidget(button)
        layout.addLayout(arrows)
        self._assign()

    def _arrow(self, glyph: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName("galleryArrow")
        button.setText(glyph)
        button.setFocusPolicy(_NO_FOCUS)
        button.setFixedSize(14, 16)
        return button

    def _assign(self) -> None:
        items = self.gallery.items
        for i, tile in enumerate(self._tiles):
            item = items[self._offset + i]
            tile.setProperty("itemId", item.id)
            tile.setIcon(QIcon(tile_pixmap(item.id, item.short or item.text,
                                           self.gallery.tile_w - 6, 44)))
            tile.setToolTip(item.text)
            tile.setChecked(item.id == self._current)
        max_offset = len(items) - len(self._tiles)
        self._up.setEnabled(self._offset > 0)
        self._down.setEnabled(self._offset < max_offset)

    def _shift(self, delta: int) -> None:
        max_offset = len(self.gallery.items) - len(self._tiles)
        self._offset = max(0, min(max_offset, self._offset + delta))
        self._assign()

    def _choose(self, item_id: str) -> None:
        self._current = item_id
        self._assign()
        self.itemChosen.emit(self.gallery.id, item_id)

    def _tile_clicked(self, tile: QToolButton, _checked: bool = False) -> None:
        self._choose(str(tile.property("itemId")))

    def _show_all(self) -> None:
        menu = QMenu(self)
        for item in self.gallery.items:
            action = menu.addAction(item.text)
            action.setCheckable(True)
            action.setChecked(item.id == self._current)
            action.triggered.connect(partial(self._menu_choice, item.id))
        menu.exec(self._more.mapToGlobal(self._more.rect().bottomLeft()))

    def _menu_choice(self, item_id: str, _checked: bool = False) -> None:
        index = [i.id for i in self.gallery.items].index(item_id)
        visible = len(self._tiles)
        if index < self._offset:
            self._offset = index
        elif index >= self._offset + visible:
            self._offset = index - visible + 1
        self._choose(item_id)

    def set_current(self, item_id: str) -> None:
        if any(i.id == item_id for i in self.gallery.items):
            self._current = item_id
            self._assign()


class RibbonBar(QWidget):
    """Quick-access toolbar, File button, tabs (with a contextual tab) and the ribbon body."""

    commandTriggered = Signal(str)
    valueChanged = Signal(str, float)

    def __init__(self, tabs: Sequence[Tab], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tabs = list(tabs)
        self._buttons: Dict[str, QToolButton] = {}
        self._galleries: Dict[str, GalleryWidget] = {}
        self._spins: Dict[str, QDoubleSpinBox] = {}
        self._widgets: Dict[str, QWidget] = {}
        self._requires: Dict[str, Optional[str]] = {}
        self._tab_buttons: Dict[str, QToolButton] = {}
        self._tab_index: Dict[str, int] = {}
        self._contextual_widget: Optional[QWidget] = None
        self._contextual_tab_id: Optional[str] = None
        self._last_regular_tab = self._tabs[0].id

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- tab row -------------------------------------------------------
        row_widget = QWidget()
        row_widget.setObjectName("ribbonTabRow")
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(6, 4, 6, 0)
        row.setSpacing(0)
        bottom = Qt.AlignmentFlag.AlignBottom

        self._qat: Dict[str, QToolButton] = {}
        for command, tip, icon_name in QUICK_ACCESS:
            button = QToolButton()
            button.setObjectName("qat")
            button.setIcon(icon(icon_name))
            button.setIconSize(QSize(16, 16))
            button.setToolTip(tip)
            button.setFocusPolicy(_NO_FOCUS)
            button.clicked.connect(partial(self._emit, command))
            row.addWidget(button, 0, bottom)
            self._qat[command] = button
        row.addSpacing(8)

        self.file_button = QToolButton()
        self.file_button.setObjectName("fileTab")
        self.file_button.setText("File")
        self.file_button.setFocusPolicy(_NO_FOCUS)
        row.addWidget(self.file_button, 0, bottom)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.body = QStackedWidget()
        self.body.setObjectName("ribbonBody")
        self.body.setFixedHeight(BODY_HEIGHT)

        for index, tab in enumerate(self._tabs):
            self._tab_index[tab.id] = index
            self.body.addWidget(self._build_page(tab))
            button = QToolButton()
            button.setText(tab.title)
            button.setCheckable(True)
            button.setFocusPolicy(_NO_FOCUS)
            button.clicked.connect(partial(self._tab_clicked, tab.id))
            self._group.addButton(button)
            self._tab_buttons[tab.id] = button
            if tab.contextual:
                button.setObjectName("contextTab")
                holder = QWidget()
                holder_layout = QVBoxLayout(holder)
                holder_layout.setContentsMargins(0, 0, 0, 0)
                holder_layout.setSpacing(0)
                header = QLabel(tab.contextual)
                header.setObjectName("contextHeader")
                header.setAlignment(Qt.AlignmentFlag.AlignCenter)
                holder_layout.addWidget(header)
                holder_layout.addWidget(button)
                holder.setVisible(False)
                row.addSpacing(10)
                row.addWidget(holder, 0, bottom)
                self._contextual_widget = holder
                self._contextual_tab_id = tab.id
            else:
                button.setObjectName("ribbonTab")
                row.addWidget(button, 0, bottom)
        row.addStretch(1)

        self.help_button = QToolButton()
        self.help_button.setObjectName("helpBtn")
        self.help_button.setText("?")
        self.help_button.setFocusPolicy(_NO_FOCUS)
        self.help_button.clicked.connect(partial(self._emit, "help.open"))
        self.collapse_button = QToolButton()
        self.collapse_button.setObjectName("collapseBtn")
        self.collapse_button.setText("\u2303")
        self.collapse_button.setToolTip("Minimize the ribbon")
        self.collapse_button.setFocusPolicy(_NO_FOCUS)
        self.collapse_button.clicked.connect(self._toggle_collapsed)
        row.addWidget(self.collapse_button, 0, bottom)
        row.addWidget(self.help_button, 0, bottom)

        root.addWidget(row_widget)
        root.addWidget(self.body)
        self.select_tab(self._tabs[0].id)

    # ---- building ---------------------------------------------------------
    def _build_page(self, tab: Tab) -> QWidget:
        page = QWidget()
        page.setObjectName("ribbonPage")
        layout = QHBoxLayout(page)
        layout.setContentsMargins(6, 4, 6, 0)
        layout.setSpacing(0)
        for i, group in enumerate(tab.groups):
            if i:
                sep = QFrame()
                sep.setObjectName("groupSep")
                layout.addWidget(sep)
            layout.addWidget(self._build_group(group))
        layout.addStretch(1)
        return page

    def _build_group(self, group: Group) -> QWidget:
        holder = QWidget()
        outer = QVBoxLayout(holder)
        outer.setContentsMargins(6, 0, 6, 0)
        outer.setSpacing(0)
        content = QHBoxLayout()
        content.setSpacing(2)
        content.setContentsMargins(0, 0, 0, 0)
        top = Qt.AlignmentFlag.AlignTop
        for slot in group.slots:
            if isinstance(slot, Button):
                content.addWidget(self._make_button(slot, large=True), 0, top)
            elif isinstance(slot, SmallColumn):
                column = QWidget()
                col_layout = QVBoxLayout(column)
                col_layout.setContentsMargins(0, 0, 0, 0)
                col_layout.setSpacing(0)
                for item in slot.items:
                    if isinstance(item, Button):
                        col_layout.addWidget(self._make_button(item, large=False))
                    else:
                        col_layout.addWidget(self._make_spin(item))
                col_layout.addStretch(1)
                content.addWidget(column, 0, top)
            elif isinstance(slot, Gallery):
                gallery = GalleryWidget(slot)
                gallery.itemChosen.connect(
                    lambda gid, iid: self.commandTriggered.emit(f"{gid}/{iid}"))
                self._galleries[slot.id] = gallery
                self._widgets[slot.id] = gallery
                self._requires[slot.id] = slot.requires
                content.addWidget(gallery, 0, top)
        content.addStretch(1)
        outer.addLayout(content)
        title = QLabel(group.title or " ")
        title.setObjectName("groupTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(title)
        return holder

    def _make_button(self, spec: Button, large: bool) -> QToolButton:
        button = QToolButton()
        button.setObjectName("ribbonLarge" if large else "ribbonSmall")
        text = spec.text + (" \u25be" if (spec.menu or spec.arrow) else "")
        button.setText(text)
        button.setIcon(icon(spec.icon))
        button.setIconSize(QSize(32, 32) if large else QSize(16, 16))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon if large
                                  else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setToolTip(spec.tooltip or spec.text.replace("\n", " "))
        button.setFocusPolicy(_NO_FOCUS)
        if large:
            button.setMinimumWidth(54)
        else:
            button.setMinimumWidth(110)
        button.setCheckable(spec.checkable)
        button.setChecked(spec.checked)
        if spec.menu:
            menu = QMenu(button)
            for item in spec.menu:
                action = menu.addAction(item.text)
                action.triggered.connect(partial(self._emit, item.id))
            button.setMenu(menu)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        else:
            button.clicked.connect(partial(self._emit, spec.id))
        self._buttons[spec.id] = button
        self._widgets[spec.id] = button
        self._requires[spec.id] = spec.requires
        return button

    def _make_spin(self, spec: Spin) -> QWidget:
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(4, 1, 0, 1)
        layout.setSpacing(4)
        layout.addWidget(QLabel(spec.label))
        box = QDoubleSpinBox()
        box.setRange(spec.minimum, spec.maximum)
        box.setSingleStep(spec.step)
        box.setValue(spec.value)
        box.setSuffix(spec.suffix)
        box.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        box.valueChanged.connect(lambda value, sid=spec.id: self.valueChanged.emit(sid, value))
        layout.addWidget(box)
        layout.addStretch(1)
        self._widgets[spec.id] = holder
        self._requires[spec.id] = spec.requires
        self._spins[spec.id] = box
        return holder

    # ---- behaviour ----------------------------------------------------------
    def _emit(self, command: str, _checked: bool = False) -> None:
        self.commandTriggered.emit(command)

    def _tab_clicked(self, tab_id: str, _checked: bool = False) -> None:
        self.select_tab(tab_id)

    def _toggle_collapsed(self) -> None:
        self.body.setVisible(not self.body.isVisible())

    def select_tab(self, tab_id: str) -> None:
        self._tab_buttons[tab_id].setChecked(True)
        self.body.setCurrentIndex(self._tab_index[tab_id])
        self.body.setVisible(True)
        if tab_id != self._contextual_tab_id:
            self._last_regular_tab = tab_id

    def current_tab(self) -> str:
        for tab_id, button in self._tab_buttons.items():
            if button.isChecked():
                return tab_id
        return self._tabs[0].id

    def set_contextual_visible(self, visible: bool) -> None:
        if self._contextual_widget is None:
            return
        self._contextual_widget.setVisible(visible)
        if not visible and self.current_tab() == self._contextual_tab_id:
            self.select_tab(self._last_regular_tab)

    def contextual_visible(self) -> bool:
        # isVisibleTo works even before the window itself has been shown
        return bool(self._contextual_widget and self._contextual_widget.isVisibleTo(self))

    def apply_state(self, has_clips: bool, has_selection: bool) -> None:
        for widget_id, widget in self._widgets.items():
            widget.setEnabled(is_enabled(self._requires.get(widget_id), has_clips, has_selection))

    def set_checked(self, button_id: str, checked: bool) -> None:
        self._buttons[button_id].setChecked(checked)

    def is_checked(self, button_id: str) -> bool:
        return self._buttons[button_id].isChecked()

    def set_gallery_current(self, gallery_id: str, item_id: str) -> None:
        gallery = self._galleries.get(gallery_id)
        if gallery is not None:
            gallery.set_current(item_id)

    def set_spin_value(self, spin_id: str, value: float) -> None:
        box = self._spins.get(spin_id)
        if box is not None:
            box.blockSignals(True)
            box.setValue(value)
            box.blockSignals(False)

    def spin_value(self, spin_id: str) -> float:
        return self._spins[spin_id].value()

    def set_qat_enabled(self, command: str, enabled: bool) -> None:
        self._qat[command].setEnabled(enabled)

    def button(self, button_id: str) -> QToolButton:
        return self._buttons[button_id]

    def is_widget_enabled(self, widget_id: str) -> bool:
        return self._widgets[widget_id].isEnabled()

    def tab_ids(self) -> List[str]:
        return [t.id for t in self._tabs]
