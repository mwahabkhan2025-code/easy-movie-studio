"""Pure timeline maths for playback: which clip plays when, and where in its source.

Preview plays the main video track one clip after another. When a transition
overlaps two clips, the earlier clip is cut where the next one begins (the
preview does not blend them; export does).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from ..model import Clip, Track

_EPS = 1e-6


@dataclass(frozen=True)
class Segment:
    index: int
    clip: Clip
    start: float  # timeline seconds
    end: float    # effective end (may be earlier than the clip's own end)

    @property
    def speed(self) -> float:
        return self.clip.speed

    @property
    def src_end(self) -> float:
        """Source position where this segment stops playing."""
        return self.source_time(self.end)

    def source_time(self, t: float) -> float:
        return self.clip.src_in + (t - self.start) * self.clip.speed

    def timeline_time(self, source_time: float) -> float:
        return self.start + (source_time - self.clip.src_in) / self.clip.speed


def build_segments(track: Track) -> List[Segment]:
    placed = track.layout()
    segments: List[Segment] = []
    for i, p in enumerate(placed):
        end = p.end
        if i + 1 < len(placed):
            end = min(end, placed[i + 1].start)
        if end - p.start > _EPS:
            segments.append(Segment(len(segments), p.clip, p.start, end))
    return segments


def total_duration(segments: Sequence[Segment]) -> float:
    return segments[-1].end if segments else 0.0


def clamp_time(segments: Sequence[Segment], t: float) -> float:
    return max(0.0, min(t, total_duration(segments)))


def segment_index_at(segments: Sequence[Segment], t: float) -> int:
    """Index of the segment playing at ``t``. The very end maps to the last segment;
    -1 only when there are no segments."""
    if not segments:
        return -1
    t = clamp_time(segments, t)
    for segment in segments:
        if segment.start - _EPS <= t < segment.end - _EPS:
            return segment.index
    return segments[-1].index


def step_time(t: float, fps: float, direction: int) -> float:
    """One frame forward (+1) or back (-1) from ``t``."""
    return t + direction / (fps if fps > 0 else 30.0)


def signature(segments: Sequence[Segment]) -> tuple:
    """Changes whenever playback would sound or look different."""
    return tuple((s.clip.id, s.clip.source, s.clip.src_in, s.clip.src_out, s.clip.speed,
                  s.clip.rotation, s.clip.volume, round(s.start, 4), round(s.end, 4))
                 for s in segments)
