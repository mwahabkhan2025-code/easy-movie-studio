"""Pure geometry for the multi-track timeline: time<->pixel conversion, track row
placement, and drag-snapping. No Qt here, so all of it is directly unit-testable.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

LEFT_MARGIN = 70.0   # space reserved for track labels down the left edge
RULER_HEIGHT = 24.0
ROW_HEIGHT = 46.0
ROW_GAP = 3.0


def time_to_x(t: float, pps: float, scroll: float = 0.0) -> float:
    return LEFT_MARGIN + (t - scroll) * pps


def x_to_time(x: float, pps: float, scroll: float = 0.0) -> float:
    return max(0.0, (x - LEFT_MARGIN) / pps + scroll) if pps > 0 else 0.0


def row_top(index: int) -> float:
    return RULER_HEIGHT + index * (ROW_HEIGHT + ROW_GAP)


def row_at_y(y: float, track_count: int) -> Optional[int]:
    if y < RULER_HEIGHT or track_count <= 0:
        return None
    index = int((y - RULER_HEIGHT) // (ROW_HEIGHT + ROW_GAP))
    if 0 <= index < track_count and y < row_top(index) + ROW_HEIGHT:
        return index
    return None


def snap_time(candidate: float, anchors: Sequence[float], threshold_seconds: float) -> float:
    """The nearest anchor within ``threshold_seconds`` of ``candidate``, else ``candidate``
    unchanged. Ties go to the closest; equidistant ties keep the first anchor given."""
    best = candidate
    best_distance = threshold_seconds
    for anchor in anchors:
        distance = abs(anchor - candidate)
        if distance < best_distance:
            best = anchor
            best_distance = distance
    return max(0.0, best)


def collect_snap_anchors(track_spans: Sequence[Sequence[Tuple[float, float]]],
                         skip_clip_span: Optional[Tuple[float, float]] = None,
                         extra: Sequence[float] = ()) -> List[float]:
    """Every clip start/end across every track (as (start, end) pairs per track),
    flattened into one sorted, de-duplicated anchor list, plus any extra anchors
    (typically the playhead and 0.0). ``skip_clip_span`` excludes the dragged clip's
    own current span so it doesn't snap to itself."""
    anchors = set(extra)
    anchors.add(0.0)
    for spans in track_spans:
        for span in spans:
            if span == skip_clip_span:
                continue
            anchors.add(span[0])
            anchors.add(span[1])
    return sorted(anchors)
