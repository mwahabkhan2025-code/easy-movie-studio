"""Entry point: ``python -m mmclone``.

Options:
  --demo              start with a made-up project so the storyboard and the
                      Video Tools tab can be explored
  --open FILE         open a project file
  --screenshots DIR   save a PNG of every ribbon tab and the File menu, then quit
  --info              print a text summary and exit (no window)
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from . import APP_NAME, __version__
from .model import Project


def _parse(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mmclone", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--demo", action="store_true", help="start with a demo project")
    parser.add_argument("--open", metavar="FILE", help="open a project file")
    parser.add_argument("--screenshots", metavar="DIR", help="save screenshots and quit")
    parser.add_argument("--info", action="store_true", help="print a summary and exit")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse(argv)
    if args.info:
        project = Project.new("Demo")
        print(f"{APP_NAME} {__version__}: new project "
              f"{project.settings.width}x{project.settings.height} @ {project.settings.fps:g} fps, "
              f"{len(project.tracks)} tracks")
        return 0

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from .demo import demo_project
    from .ui.icons import app_icon
    from .ui.main_window import MainWindow
    from .ui.theme import stylesheet

    if sys.platform == "win32":
        import ctypes
        try:  # groups the taskbar icon under our own app instead of generic python.exe
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                f"MovieStudio.{APP_NAME}.{__version__}")
        except Exception:
            pass

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 9))
    app.setStyleSheet(stylesheet())
    icon = app_icon()
    app.setWindowIcon(icon)

    from . import crashlog

    def on_crash(summary: str, log_path: str) -> None:
        # A packaged .exe has no console for the person to see this in otherwise --
        # the window would just vanish with no explanation at all.
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox(QMessageBox.Icon.Critical, APP_NAME,
                          f"{APP_NAME} ran into an unexpected problem and needs to close.\n\n"
                          f"{summary}\n\nDetails were saved to:\n{log_path}")
        box.exec()

    crashlog.install(on_crash)

    window = MainWindow(demo_project() if args.demo else None, verify_media=not args.demo)
    window.setWindowIcon(icon)
    window.show()
    if args.open:
        window.on_command(f"file.open_recent:{args.open}")
    if args.screenshots:
        def capture() -> None:
            saved = window.capture_screenshots(args.screenshots)
            print("Saved screenshots:")
            for path in saved:
                print("  " + path)
            app.quit()
        QTimer.singleShot(600, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
