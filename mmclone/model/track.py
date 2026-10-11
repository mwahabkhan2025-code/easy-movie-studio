"""Track: an ordered lane of clips.

Ripple tracks (the storyboard / main video track) place clips back to back;
their timeline position is computed. Non-ripple tracks (music, overlays) use
each clip's explicit ``start``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .clip import KIND_AUDIO, KIND_IMAGE, KIND_TITLE, KIND_VIDEO, Clip, new_id

TRACK_VIDEO = "video"
TRACK_AUDIO = "audio"
_ACCEPTS = {
    TRACK_VIDEO: (KIND_VIDEO, KIND_IMAGE, KIND_TITLE),
    TRACK_AUDIO: (KIND_AUDIO,),
}
_EDGE = 1e-3  # seconds; splits closer than this to a clip edge are rejected


@dataclass
class PlacedClip:
    """A clip together with its computed position on the timeline."""

    clip: Clip
    start: float
    end: float
    overlap: float = 0.0  # seconds overlapping the previous clip (transition)


@dataclass
class Track:
    kind: str
    name: str = ""
    ripple: bool = True
    muted: bool = False
    locked: bool = False
    id: str = field(default_factory=new_id)
    clips: List[Clip] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.kind not in _ACCEPTS:
            raise ValueError(f"Unknown track kind: {self.kind!r}")

    # ---- lookup -----------------------------------------------------------
    def index_of(self, clip_id: str) -> int:
        for i, clip in enumerate(self.clips):
            if clip.id == clip_id:
                return i
        raise KeyError(clip_id)

    def get_clip(self, clip_id: str) -> Clip:
        return self.clips[self.index_of(clip_id)]

    # ---- layout -----------------------------------------------------------
    @staticmethod
    def transition_overlap(prev: Clip, clip: Clip) -> float:
        """Overlap (seconds) for the transition into ``clip``.

        Capped at half of each neighbouring clip so that two transitions on
        one clip can never collide.
        """
        if clip.transition_in is None:
            return 0.0
        return max(0.0, min(clip.transition_in.duration, prev.duration / 2, clip.duration / 2))

    def layout(self) -> List[PlacedClip]:
        placed: List[PlacedClip] = []
        if self.ripple:
            cursor = 0.0
            prev: Optional[Clip] = None
            for clip in self.clips:
                overlap = self.transition_overlap(prev, clip) if prev is not None else 0.0
                start = cursor - overlap
                end = start + clip.duration
                placed.append(PlacedClip(clip, start, end, overlap))
                cursor = end
                prev = clip
        else:
            for clip in sorted(self.clips, key=lambda c: c.start):
                placed.append(PlacedClip(clip, clip.start, clip.start + clip.duration))
        return placed

    @property
    def duration(self) -> float:
        layout = self.layout()
        return max((p.end for p in layout), default=0.0)

    def clip_at(self, t: float) -> Optional[PlacedClip]:
        """Clip playing at time ``t`` (the later clip during a transition)."""
        hit: Optional[PlacedClip] = None
        for p in self.layout():
            if p.start <= t < p.end:
                hit = p
        return hit

    def set_ripple(self, ripple: bool) -> None:
        """Switch mode; when leaving ripple mode, freeze current positions."""
        if ripple == self.ripple:
            return
        if not ripple:
            for p in self.layout():
                p.clip.start = p.start
        self.ripple = ripple

    # ---- editing ----------------------------------------------------------
    def add_clip(self, clip: Clip, index: Optional[int] = None) -> Clip:
        if clip.kind not in _ACCEPTS[self.kind]:
            raise ValueError(f"A {self.kind} track cannot hold a {clip.kind} clip")
        if any(c.id == clip.id for c in self.clips):
            raise ValueError("Clip is already on this track")
        if index is None:
            self.clips.append(clip)
        else:
            self.clips.insert(index, clip)
        return clip

    def remove_clip(self, clip_id: str) -> Clip:
        return self.clips.pop(self.index_of(clip_id))

    def move_clip(self, clip_id: str, new_index: int) -> None:
        """Reorder: ``new_index`` is the clip's position after the move."""
        if not (0 <= new_index < len(self.clips)):
            raise IndexError(new_index)
        clip = self.clips.pop(self.index_of(clip_id))
        self.clips.insert(new_index, clip)

    def split_clip(self, clip_id: str, at: float) -> Clip:
        """Split a clip at track time ``at``; returns the new second half."""
        placed = next((p for p in self.layout() if p.clip.id == clip_id), None)
        if placed is None:
            raise KeyError(clip_id)
        if not (placed.start + _EDGE < at < placed.end - _EDGE):
            raise ValueError("Split point must be inside the clip")
        clip = placed.clip
        offset = clip.src_in + (at - placed.start) * clip.speed
        second = clip.duplicate()
        second.update(src_in=offset, transition_in=None, fade_in=0.0)
        if not self.ripple:
            second.update(start=at)
        clip.update(src_out=offset, fade_out=0.0)
        self.clips.insert(self.index_of(clip_id) + 1, second)
        return second

    # ---- serialization ----------------------------------------------------
    def to_dict(self, base_dir: Optional[str] = None) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "ripple": self.ripple,
            "muted": self.muted,
            "locked": self.locked,
            "clips": [c.to_dict(base_dir) for c in self.clips],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], base_dir: Optional[str] = None) -> "Track":
        return cls(
            kind=data["kind"],
            name=data.get("name", ""),
            ripple=data.get("ripple", True),
            muted=data.get("muted", False),
            locked=data.get("locked", False),
            id=data.get("id") or new_id(),
            clips=[Clip.from_dict(c, base_dir) for c in data.get("clips", [])],
        )
