"""Runs an export plan through FFmpeg, reporting progress as it goes.

Progress comes from FFmpeg's own ``-progress`` stream (key=value lines on a
pipe), which is far more reliable than scraping the human-readable stderr log.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from typing import Callable, List, Optional

from .export_plan import ExportPlan
from .tools import find_ffmpeg

_TIME_RE = re.compile(r"out_time_ms=(\d+)")
_TIME_US_RE = re.compile(r"out_time_us=(\d+)")


class ExportRunError(Exception):
    def __init__(self, message: str, log_tail: str = "") -> None:
        super().__init__(message)
        self.log_tail = log_tail


@dataclass
class ExportHandle:
    """Returned immediately so the caller (a progress dialog) can cancel."""

    process: subprocess.Popen
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True
        if self.process.poll() is None:
            self.process.terminate()


def run_export(plan: ExportPlan, on_progress: Optional[Callable[[float], None]] = None,
               on_handle: Optional[Callable[[ExportHandle], None]] = None) -> None:
    """Runs synchronously (call this from a worker thread, not the GUI thread).

    ``on_progress`` receives a fraction 0..1. ``on_handle`` is called immediately
    with an ExportHandle so the caller can cancel from another thread.
    Raises ExportRunError on failure or cancellation.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise ExportRunError("FFmpeg was not found. Install the requirements or set "
                             "EASY_MOVIE_STUDIO_FFMPEG_DIR.")
    out_dir = os.path.dirname(plan.output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    args = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
           *plan.args[:-1], "-progress", "pipe:1", plan.args[-1]]
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               stdin=subprocess.DEVNULL, text=True, **kwargs)
    handle = ExportHandle(process)
    if on_handle is not None:
        on_handle(handle)

    stderr_lines: List[str] = []
    try:
        assert process.stdout is not None
        for line in process.stdout:
            match = _TIME_US_RE.search(line) or _TIME_RE.search(line)
            if match and on_progress is not None and plan.duration > 0:
                seconds = int(match.group(1)) / (1_000_000 if "us=" in line else 1000)
                on_progress(min(1.0, max(0.0, seconds / plan.duration)))
        if process.stderr is not None:
            stderr_lines = process.stderr.readlines()
        process.wait()
    finally:
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()

    if handle.cancelled:
        _remove_partial(plan.output_path)
        raise ExportRunError("Export cancelled.")
    if process.returncode != 0:
        _remove_partial(plan.output_path)
        tail = "".join(stderr_lines[-15:]).strip()
        raise ExportRunError("FFmpeg could not export the movie.", log_tail=tail)
    if on_progress is not None:
        on_progress(1.0)


def _remove_partial(path: str) -> None:
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass
