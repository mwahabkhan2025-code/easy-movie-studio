"""Renders a title or credits card to a PNG file using Pillow.

The rendered PNG is then treated exactly like a photo everywhere else in the
app (thumbnails, preview stills, export input) -- see KIND_TITLE / STATIC_KINDS
in the model. Files are cached by content hash so re-opening a project with
unchanged titles doesn't re-render them.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from functools import lru_cache
from typing import List, Optional, Sequence, Tuple

CACHE_DIR = os.path.join(tempfile.gettempdir(), "mmclone_titles")

# Searched in order; the first that exists on this machine is used. Covers common
# Windows fonts, common Linux fonts, and the fonts bundled with this app's skills
# environment (handy for testing where neither of the above is installed).
_BOLD_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)
_REGULAR_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)

_BG_PRESETS = {
    "black": "#101010", "white": "#f5f5f5", "dark blue": "#0e1a33",
    "dark red": "#330d0d", "gray": "#2b2b2b",
}


class TitleRenderError(Exception):
    pass


@lru_cache(maxsize=1)
def find_font_path(bold: bool = True) -> Optional[str]:
    for path in (_BOLD_FONT_CANDIDATES if bold else _REGULAR_FONT_CANDIDATES):
        if os.path.isfile(path):
            return path
    return None


def resolve_background(value: str) -> str:
    """Accepts a hex color ("#112233") or one of the named presets, case-insensitively."""
    return _BG_PRESETS.get(value.strip().lower(), value)


def _cache_path(payload: dict, suffix: str = ".png") -> str:
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{digest}{suffix}")


def caption_text_file(text: str) -> str:
    """Writes a caption's text verbatim to a small cached .txt file and returns its path.

    FFmpeg's drawtext filter reads the file as-is (UTF-8), so unlike drawtext's inline
    ``text=`` option, nothing in the caption itself needs filter-syntax escaping.
    """
    path = _cache_path({"caption": text}, suffix=".txt")
    if os.path.isfile(path):
        return path
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp_path = path + f".{os.getpid()}.tmp"
    with open(tmp_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    os.replace(tmp_path, path)
    return path


def _load_font(size: int, bold: bool = True):
    from PIL import ImageFont
    path = find_font_path(bold)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _wrap_text(draw, text: str, font, max_width: int) -> List[str]:
    lines: List[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _draw_centered_block(draw, lines: Sequence[Tuple[str, "object"]], center_y: float,
                         width: int, line_gap: int = 10) -> None:
    """``lines`` is (text, font) pairs. Draws them stacked, each horizontally centered,
    vertically centered as a block around ``center_y``."""
    heights = [draw.textbbox((0, 0), text or " ", font=font)[3] for text, font in lines]
    total = sum(heights) + line_gap * max(0, len(lines) - 1)
    y = center_y - total / 2
    for (text, font), height in zip(lines, heights):
        box = draw.textbbox((0, 0), text or " ", font=font)
        x = (width - (box[2] - box[0])) / 2
        draw.text((x, y), text, font=font, fill="#ffffff")
        y += height + line_gap


def render_title_png(text: str, width: int, height: int, style: str = "title",
                     background: str = "#101010", lines: Optional[List[List[str]]] = None
                     ) -> str:
    """Renders (or reuses a cached render of) a title/credits card. Returns the PNG path."""
    from PIL import Image, ImageDraw

    width, height = max(16, int(width)), max(16, int(height))
    background = resolve_background(background)
    key_lines = [list(pair) for pair in lines] if lines else None
    path = _cache_path({"text": text, "width": width, "height": height, "style": style,
                        "background": background, "lines": key_lines})
    if os.path.isfile(path):
        return path

    try:
        image = Image.new("RGB", (width, height), background)
    except ValueError as exc:
        raise TitleRenderError(f"'{background}' isn't a color FFmpeg/Pillow understands") from exc
    draw = ImageDraw.Draw(image)
    margin = int(width * 0.1)
    max_width = width - 2 * margin

    if style == "credits" and lines:
        role_font = _load_font(max(14, height // 22), bold=False)
        name_font = _load_font(max(20, height // 14), bold=True)
        blocks: List[Tuple[str, object]] = []
        for role, name in lines:
            if role.strip():
                blocks.append((role.strip(), role_font))
            if name.strip():
                blocks.append((name.strip(), name_font))
        if blocks:
            _draw_centered_block(draw, blocks, height / 2, width)
    else:
        font = _load_font(max(24, height // 12), bold=True)
        wrapped = _wrap_text(draw, text or " ", font, max_width)
        _draw_centered_block(draw, [(line, font) for line in wrapped], height / 2, width)

    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp_path = path + f".{os.getpid()}.tmp"
    image.save(tmp_path, "PNG")
    os.replace(tmp_path, path)
    return path
