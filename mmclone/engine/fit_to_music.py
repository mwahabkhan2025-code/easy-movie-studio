"""Pure arithmetic for "Fit to music": stretches or shrinks the last clip on the
main track so the movie's total length matches the Music track's length.

Only the last clip is adjusted (simpler and less disruptive than rescaling
every clip's speed). A photo or title card has no hard length limit, so it can
always be matched exactly; a real video clip is capped at how much of its
source actually exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..model import Project
from ..model.clip import MIN_SOURCE_LENGTH

_EPS = 1e-6


@dataclass(frozen=True)
class FitResult:
    clip_id: str
    new_in: float
    new_out: float
    matched_exactly: bool
    target_duration: float


def compute_fit_to_music(project: Project) -> Optional[FitResult]:
    main = project.main_track
    if not main.clips:
        return None
    target = max((t.duration for t in project.tracks if t.kind == "audio"), default=0.0)
    if target <= 0:
        return None

    last = main.clips[-1]
    delta = target - main.duration
    if abs(delta) < _EPS:
        return None  # already matches

    desired_duration = max(MIN_SOURCE_LENGTH, last.duration + delta)
    matched_exactly = True
    if last.media_duration is not None:
        max_duration = (last.media_duration - last.src_in) / last.speed
        if desired_duration > max_duration + _EPS:
            desired_duration = max_duration
            matched_exactly = False
        if desired_duration < MIN_SOURCE_LENGTH:
            desired_duration = MIN_SOURCE_LENGTH
            matched_exactly = False

    new_out = last.src_in + desired_duration * last.speed
    if abs(new_out - last.src_out) < _EPS:
        return None
    return FitResult(last.id, last.src_in, new_out, matched_exactly, target)
