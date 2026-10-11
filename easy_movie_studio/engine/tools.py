"""Locating and running the FFmpeg command-line tools.

Search order: the folder in the EASY_MOVIE_STUDIO_FFMPEG_DIR environment variable, then the
folder the app itself is running from (so dropping ffmpeg.exe/ffprobe.exe next to a
packaged EasyMovieStudio.exe just works, with no environment variable to set), then PATH,
then the ffmpeg binary bundled with the ``imageio-ffmpeg`` package. Note that
imageio-ffmpeg ships ``ffmpeg`` only (no ``ffprobe``), so media probing has a fallback
that reads the output of ``ffmpeg -i``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Optional, Sequence


def _bundled_ffmpeg() -> Optional[str]:
    try:
        import imageio_ffmpeg
        path = imageio_ffmpeg.get_ffmpeg_exe()
        return path if path and os.path.isfile(path) else None
    except Exception:
        return None


def _app_dir() -> Optional[str]:
    """Where the running app itself lives: the packaged .exe's own folder when frozen
    by PyInstaller (``sys.frozen``), or this source file's folder otherwise."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return None


def _search_dirs() -> Sequence[str]:
    dirs = []
    env_dir = os.environ.get("EASY_MOVIE_STUDIO_FFMPEG_DIR")
    if env_dir:
        dirs.append(env_dir)
    app_dir = _app_dir()
    if app_dir:
        dirs.append(app_dir)
    return dirs


def find_tool(name: str) -> Optional[str]:
    for directory in _search_dirs():
        for candidate in (name, name + ".exe"):
            path = os.path.join(directory, candidate)
            if os.path.isfile(path):
                return path
    found = shutil.which(name)
    if found:
        return found
    if name == "ffmpeg":
        return _bundled_ffmpeg()
    return None


def find_ffmpeg() -> Optional[str]:
    return find_tool("ffmpeg")


def find_ffprobe() -> Optional[str]:
    return find_tool("ffprobe")


def run_tool(args: Sequence[str], timeout: float = 60.0) -> "subprocess.CompletedProcess[bytes]":
    """Run a tool without flashing a console window on Windows."""
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    return subprocess.run(list(args), capture_output=True, timeout=timeout,
                          stdin=subprocess.DEVNULL, **kwargs)
