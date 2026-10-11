"""Extract single frames from videos and photos as PNG bytes (Qt-free)."""

from __future__ import annotations

from typing import Optional

from .tools import find_ffmpeg, run_tool

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class ThumbnailError(Exception):
    pass


def _grab(path: str, time: Optional[float], height: int) -> bytes:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise ThumbnailError("FFmpeg was not found")
    args = [ffmpeg, "-v", "error", "-nostdin"]
    if time is not None and time > 0:
        args += ["-ss", f"{time:.3f}"]
    args += ["-i", path, "-frames:v", "1", "-vf", f"scale=-2:{int(height)}",
             "-f", "image2pipe", "-vcodec", "png", "-"]
    result = run_tool(args, timeout=30)
    return result.stdout if result.stdout.startswith(_PNG_SIGNATURE) else b""


def extract_frame_png(path: str, time: Optional[float], height: int) -> bytes:
    """One frame as PNG, scaled to ``height`` pixels tall.

    ``time`` is seconds into the file, or None for photos. If the requested
    time is past the last frame, the first frame is returned instead.
    """
    try:
        data = _grab(path, time, height)
        if not data and time:
            data = _grab(path, None, height)
    except OSError as exc:
        raise ThumbnailError(str(exc)) from exc
    if not data:
        raise ThumbnailError("Could not decode a frame")
    return data
