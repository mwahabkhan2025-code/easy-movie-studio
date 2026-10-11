"""Pure geometry for the storyboard: where each clip block goes."""

from __future__ import annotations

from typing import List, Sequence, Tuple

Rect = Tuple[float, float, float, float]  # x, y, width, height


def layout_clips(durations: Sequence[float], pps: float, available_width: float,
                 row_height: float, gap: float = 8.0, margin: float = 12.0,
                 min_width: float = 64.0) -> Tuple[List[Rect], float]:
    """Place clip blocks left to right, wrapping to a new row when full.

    Width is proportional to duration (``pps`` pixels per second), never below
    ``min_width`` or above the available width. Returns (rects, total_height).
    """
    max_w = max(min_width, available_width - 2 * margin)
    rects: List[Rect] = []
    x = margin
    y = margin
    for duration in durations:
        w = min(max(duration * pps, min_width), max_w)
        if x > margin and x + w > available_width - margin:
            x = margin
            y += row_height + gap
        rects.append((x, y, w, row_height))
        x += w + gap
    total_height = y + row_height + margin if durations else 0.0
    return rects, total_height


def hit_test(rects: Sequence[Rect], px: float, py: float) -> int:
    """Index of the rect containing the point, or -1."""
    for i, (x, y, w, h) in enumerate(rects):
        if x <= px <= x + w and y <= py <= y + h:
            return i
    return -1


def cover_source_rect(image_w: float, image_h: float, target_w: float,
                      target_h: float) -> tuple:
    """Source rectangle (x, y, w, h) that fills the target by cropping the centre."""
    if image_w <= 0 or image_h <= 0 or target_w <= 0 or target_h <= 0:
        return (0.0, 0.0, max(image_w, 1.0), max(image_h, 1.0))
    target_ratio = target_w / target_h
    if image_w / image_h > target_ratio:
        w = image_h * target_ratio
        return ((image_w - w) / 2, 0.0, w, image_h)
    h = image_w / target_ratio
    return (0.0, (image_h - h) / 2, image_w, h)


def edge_hit(rect, px: float, margin: float = 8.0) -> "str | None":
    """'left' or 'right' if ``px`` is within ``margin`` of that edge of ``rect``,
    else None. Used to grab a clip's edge for trimming."""
    x, _y, w, _h = rect
    if px <= x + margin:
        return "left"
    if px >= x + w - margin:
        return "right"
    return None


def insertion_index(rects, px: float, py: float) -> int:
    """Where a dragged item should land among ``rects`` (already excluding it),
    which are in left-to-right, top-to-bottom visual order. Returns an index in
    0..len(rects), suitable for Track.move_clip after the dragged clip is popped."""
    if not rects:
        return 0
    rows = []  # list of (y, [indices into rects])
    for i, (_x, y, _w, _h) in enumerate(rects):
        if rows and abs(rows[-1][0] - y) < 1e-6:
            rows[-1][1].append(i)
        else:
            rows.append((y, [i]))
    chosen = None
    for y, indices in rows:
        h = rects[indices[0]][3]
        if y - 2 <= py <= y + h + 2:
            chosen = indices
            break
    if chosen is None:
        def row_distance(row):
            y, indices = row
            h = rects[indices[0]][3]
            return abs(py - (y + h / 2))
        chosen = min(rows, key=row_distance)[1]
    for index in chosen:
        x, _y, w, _h = rects[index]
        if px < x + w / 2:
            return index
    return chosen[-1] + 1
