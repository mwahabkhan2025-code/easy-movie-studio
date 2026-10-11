"""Colours and the application stylesheet (Windows Movie Maker 2012 look).

Pure Python: no Qt imports, so it can be tested anywhere.
"""

from __future__ import annotations

from string import Template

COLORS = {
    "file_blue": "#1979CA",
    "file_blue_hover": "#2b8ae0",
    "file_blue_pressed": "#12609f",
    "icon": "#2f7fc1",
    "icon_disabled": "#b5c0cc",
    "text": "#333333",
    "text_muted": "#68737f",
    "status_text": "#4d7ea8",
    "border": "#d5d9de",
    "ribbon_top": "#fbfcfd",
    "ribbon_bottom": "#f0f2f4",
    "context_yellow": "#f8f3a4",
    "context_border": "#e2db8c",
    "hover_bg": "#e3f0fb",
    "hover_border": "#a9cbe8",
    "pressed_bg": "#cfe4f7",
    "pressed_border": "#7fb2dd",
    "dash_blue": "#9fcdee",
    "select_blue": "#4aa3df",
}

_QSS = Template(r"""
* { font-family: "Segoe UI", "Noto Sans", "DejaVu Sans", sans-serif; font-size: 9pt; color: $text; }
QMainWindow, QWidget#centralRoot { background: #ffffff; }
QToolTip { background: #ffffff; color: $text; border: 1px solid #a3adb8; padding: 3px; }

/* ---- tab row ---- */
QWidget#ribbonTabRow { background: #ffffff; }
QToolButton#fileTab { background: $file_blue; color: #ffffff; border: none; padding: 4px 18px; min-height: 22px; font-weight: bold; }
QToolButton#fileTab:hover { background: $file_blue_hover; }
QToolButton#fileTab:pressed { background: $file_blue_pressed; }
QToolButton#ribbonTab, QToolButton#contextTab { background: transparent; border: 1px solid transparent; border-bottom: none; padding: 4px 12px; min-height: 22px; }
QToolButton#ribbonTab:hover { background: $hover_bg; }
QToolButton#ribbonTab:checked { background: $ribbon_top; border-color: $border; }
QToolButton#contextTab { background: $context_yellow; border-color: $context_border; }
QToolButton#contextTab:checked { background: $ribbon_top; }
QLabel#contextHeader { background: $context_yellow; border: 1px solid $context_border; border-bottom: none; padding: 1px 12px; color: #4a4a3a; }
QToolButton#qat { background: transparent; border: 1px solid transparent; padding: 2px; }
QToolButton#qat:hover { background: $hover_bg; border-color: $hover_border; }
QToolButton#helpBtn { background: $file_blue; color: #ffffff; border: none; border-radius: 9px; min-width: 18px; max-width: 18px; min-height: 18px; max-height: 18px; font-weight: bold; }
QToolButton#collapseBtn { background: transparent; border: none; color: $text_muted; padding: 2px 6px; }

/* ---- ribbon body ---- */
QStackedWidget#ribbonBody { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 $ribbon_top, stop:1 $ribbon_bottom); border-top: 1px solid $border; border-bottom: 1px solid $border; }
QWidget#ribbonPage { background: transparent; }
QLabel#groupTitle { color: $text_muted; padding: 0 0 2px 0; }
QFrame#groupSep { background: #dcdfe3; border: none; min-width: 1px; max-width: 1px; }
QToolButton#ribbonLarge, QToolButton#ribbonSmall { background: transparent; border: 1px solid transparent; border-radius: 2px; padding: 2px 4px; }
QToolButton#ribbonLarge:hover, QToolButton#ribbonSmall:hover { background: $hover_bg; border-color: $hover_border; }
QToolButton#ribbonLarge:pressed, QToolButton#ribbonSmall:pressed, QToolButton#ribbonLarge:checked, QToolButton#ribbonSmall:checked { background: $pressed_bg; border-color: $pressed_border; }
QToolButton#ribbonLarge:disabled, QToolButton#ribbonSmall:disabled { color: #a3adb8; }
QToolButton::menu-indicator { image: none; width: 0px; }
QToolButton#galleryTile { background: #ffffff; border: 1px solid #c7ced6; padding: 1px; }
QToolButton#galleryTile:hover { border-color: #6aaee0; }
QToolButton#galleryTile:checked { border: 2px solid #3d97dc; padding: 0px; }
QToolButton#galleryTile:disabled { border-color: #dde2e8; }
QToolButton#galleryArrow { background: #eef1f4; border: 1px solid #d3d9df; color: #7a8794; min-width: 14px; max-width: 14px; min-height: 14px; padding: 0; font-size: 6pt; }
QToolButton#galleryArrow:hover { background: $hover_bg; }
QToolButton#galleryArrow:disabled { color: #c3cad2; }
QDoubleSpinBox { background: #ffffff; border: 1px solid #c4ccd4; padding: 1px 2px; }
QDoubleSpinBox:disabled { background: #f1f3f5; color: #a3adb8; }

/* ---- workspace ---- */
QWidget#workspace { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #e8eff8, stop:0.06 #ffffff, stop:0.92 #ffffff, stop:1 #edf2f8); }
QSplitter::handle:horizontal { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 transparent, stop:0.45 transparent, stop:0.5 #cdd5de, stop:0.55 transparent, stop:1 transparent); }
QScrollArea#storyScroll { background: transparent; border: none; }
QScrollArea#storyScroll > QWidget > QWidget { background: transparent; }
QLabel#timeLabel { color: #555b62; }
QToolButton#previewFull { background: transparent; border: 1px solid transparent; padding: 1px; }
QToolButton#previewFull:hover { background: $hover_bg; border-color: $hover_border; }
QSlider::groove:horizontal { height: 2px; background: #8e99a6; }
QSlider::handle:horizontal { background: #f4f6f8; border: 1px solid #7f8b99; width: 10px; height: 10px; margin: -5px 0; border-radius: 5px; }
QSlider::handle:horizontal:disabled { border-color: #c3cad2; }
QToolButton#transportLeft, QToolButton#transportMid, QToolButton#transportRight { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f8fafc, stop:1 #dfe5eb); border: 1px solid #a5b0bc; padding: 3px 12px; }
QToolButton#transportLeft { border-top-left-radius: 11px; border-bottom-left-radius: 11px; }
QToolButton#transportRight { border-top-right-radius: 11px; border-bottom-right-radius: 11px; }
QToolButton#transportLeft:hover, QToolButton#transportMid:hover, QToolButton#transportRight:hover { background: $hover_bg; }
QToolButton#transportLeft:disabled, QToolButton#transportMid:disabled, QToolButton#transportRight:disabled { background: #f3f5f7; border-color: #d0d6dc; }

/* ---- status bar ---- */
QStatusBar { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f8fafc, stop:1 #eaeff5); border-top: 1px solid $border; color: $status_text; }
QStatusBar::item { border: none; }
QStatusBar QLabel { color: $status_text; }
QToolButton#zoomBtn { background: transparent; border: none; padding: 1px; }

/* ---- File menu panel ---- */
QFrame#fileMenu { background: #ffffff; border: 1px solid #8fa0b3; }
QFrame#fileMenuLeft { background: #f3f5f8; border: none; border-right: 1px solid #d5dbe2; }
QPushButton#fileRow { text-align: left; padding: 8px 12px 8px 14px; border: none; background: transparent; }
QPushButton#fileRow:hover { background: #dcebf8; }
QFrame#fileSep { background: #d9dee4; border: none; max-height: 1px; min-height: 1px; margin: 3px 8px; }
QLabel#recentTitle { font-weight: bold; padding: 10px 14px 6px 14px; color: #4a5a6a; }
QPushButton#recentRow { text-align: left; padding: 6px 14px; border: none; background: transparent; }
QPushButton#recentRow:hover { background: #dcebf8; }
QMenu { background: #ffffff; border: 1px solid #b9c3ce; padding: 2px; }
QMenu::item { padding: 5px 28px 5px 24px; }
QMenu::item:selected { background: $pressed_bg; color: #000000; }
QMenu::item:disabled { color: #a3adb8; }
QMenu::separator { height: 1px; background: #dde2e8; margin: 3px 6px; }
""")


def stylesheet() -> str:
    return _QSS.substitute(COLORS)
