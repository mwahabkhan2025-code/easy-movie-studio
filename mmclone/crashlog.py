"""A global exception hook so an unexpected bug shows the person a plain message and a
saved log file, instead of the window just vanishing (the default behaviour of an
uncaught exception in a packaged, console-less .exe -- there's no terminal for the
person to see a traceback in, so without this the app would simply disappear with no
explanation at all).

This is deliberately framework-agnostic (no PySide6 import at module load time) so it
can be unit tested without Qt, and installed as early as possible in ``__main__``,
before the QApplication exists.
"""

from __future__ import annotations

import datetime
import os
import platform
import sys
import tempfile
import traceback
from typing import Callable, Optional

from . import APP_NAME, __version__

_on_crash: Optional[Callable[[str, str], None]] = None
_previous_hook = None


def log_dir() -> str:
    """Where crash logs are written: the platform's per-user local app-data folder
    when one is available (so they survive the temp folder being cleaned out), the
    system temp folder otherwise."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_STATE_HOME")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".local", "state") \
            if os.name != "nt" else tempfile.gettempdir()
    return os.path.join(base, "MovieStudio", "crash_logs")


def write_crash_log(exc_type, exc_value, tb) -> str:
    """Writes one timestamped log file with the full traceback plus enough context to
    reproduce it, and returns its path. Never raises -- a failure while writing the
    crash log falls back to the temp folder rather than losing the report entirely."""
    text = "".join(traceback.format_exception(exc_type, exc_value, tb))
    header = (f"{APP_NAME} {__version__}\n"
             f"{datetime.datetime.now().isoformat()}\n"
             f"Python {sys.version}\n"
             f"{platform.platform()}\n"
             f"{'-' * 60}\n")
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    directory = log_dir()
    try:
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"crash_{stamp}.log")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(header + text)
        return path
    except OSError:
        path = os.path.join(tempfile.gettempdir(), f"moviestudio_crash_{stamp}.log")
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(header + text)
        except OSError:
            pass  # truly nowhere writable -- the exception still prints to stderr below
        return path


def _hook(exc_type, exc_value, tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        if _previous_hook:
            _previous_hook(exc_type, exc_value, tb)
        return
    traceback.print_exception(exc_type, exc_value, tb)  # still visible when run from a console
    path = write_crash_log(exc_type, exc_value, tb)
    summary = "".join(traceback.format_exception_only(exc_type, exc_value)).strip()
    if _on_crash is not None:
        try:
            _on_crash(summary, path)
        except Exception:
            pass  # the crash handler itself must never cause a second crash


def install(on_crash: Optional[Callable[[str, str], None]] = None) -> None:
    """Installs the hook. ``on_crash(summary, log_path)`` is called after the log is
    written -- typically to show a message box; omit it to just log and print."""
    global _on_crash, _previous_hook
    _on_crash = on_crash
    _previous_hook = sys.excepthook
    sys.excepthook = _hook
