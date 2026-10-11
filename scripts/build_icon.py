"""Renders the application icon to a Windows .ico file for PyInstaller's --icon flag.

PyInstaller needs a real file on disk at build time; the app's own icons.app_icon()
only ever builds a QIcon in memory (it needs a running QApplication, drawn fresh every
launch, with qtawesome's glyph as the finishing touch). This script runs that same
app_icon() once, offscreen, and saves every size it generates into one multi-resolution
.ico so Windows can pick the sharpest one for the title bar, taskbar, and Explorer.

Usage:  python scripts/build_icon.py [output.ico]
"""

from __future__ import annotations

import io
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SIZES = (16, 24, 32, 48, 64, 128, 256)


def build(output_path: str) -> None:
    from PIL import Image
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize
    from PySide6.QtWidgets import QApplication

    from easy_movie_studio.ui.icons import app_icon

    app = QApplication.instance() or QApplication([])
    icon = app_icon()

    frames = []
    for size in _SIZES:
        pixmap = icon.pixmap(QSize(size, size))
        buf = QByteArray()
        device = QBuffer(buf)
        device.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(device, "PNG")
        frames.append(Image.open(io.BytesIO(buf.data())).convert("RGBA"))

    largest = frames[-1]
    largest.save(output_path, format="ICO",
                sizes=[(f.width, f.height) for f in frames])
    print(f"Wrote {output_path} ({len(frames)} sizes: "
         f"{', '.join(str(s) for s in _SIZES)})")
    app.quit()


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "app_icon.ico")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    build(out)
