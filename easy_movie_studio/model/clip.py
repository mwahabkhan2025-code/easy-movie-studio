"""Clip and Transition: the building blocks placed on tracks.

Times are in seconds. ``src_in``/``src_out`` are positions inside the source
file; ``duration`` is how long the clip lasts on the timeline (after speed).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields, replace
from typing import Any, Dict, List, Optional

from .paths import decode_path, encode_path

KIND_VIDEO = "video"
KIND_IMAGE = "image"
KIND_AUDIO = "audio"
KIND_TITLE = "title"  # a rendered text card (a title or a credits list) -- behaves like a photo
CLIP_KINDS = (KIND_VIDEO, KIND_IMAGE, KIND_AUDIO, KIND_TITLE)
STATIC_KINDS = (KIND_IMAGE, KIND_TITLE)  # "it's basically a still picture" for playback/thumbnails

DEFAULT_IMAGE_DURATION = 7.0
MIN_SOURCE_LENGTH = 0.05
MIN_SPEED = 0.125
MAX_SPEED = 64.0
MAX_VOLUME = 2.0
VALID_ROTATIONS = (0, 90, 180, 270)
_EPS = 1e-6


def new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class Transition:
    """A transition into a clip from the previous clip on the same track."""

    name: str
    duration: float = 1.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Transition name must not be empty")
        if self.duration < 0:
            raise ValueError("Transition duration must be >= 0")

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "duration": self.duration}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Transition":
        return cls(name=data["name"], duration=float(data.get("duration", 1.0)))


@dataclass
class Clip:
    source: str
    kind: str = KIND_VIDEO
    src_in: float = 0.0
    src_out: float = 0.0
    media_duration: Optional[float] = None  # None for still images
    id: str = field(default_factory=new_id)
    start: float = 0.0  # only used on non-ripple tracks
    speed: float = 1.0
    volume: float = 1.0
    rotation: int = 0
    effect: Optional[str] = None
    brightness: float = 0.0  # -1.0 .. 1.0
    pan_zoom: Optional[str] = None
    fade_in: float = 0.0
    fade_out: float = 0.0
    transition_in: Optional[Transition] = None
    text: str = ""                              # title/credits text (KIND_TITLE only)
    text_style: str = "title"                    # "title" or "credits"
    text_background: str = "#101010"              # hex color behind the text
    text_lines: Optional[List[List[str]]] = None  # credits only: [[role, name], ...]
    caption_text: str = ""                        # burned-in caption on an ordinary clip
    caption_position: str = "bottom"               # "top", "middle", or "bottom"
    # Picture-in-picture placement, used only for a clip on a non-main (overlay) video track.
    overlay_x: float = 0.75     # fraction of frame width where the overlay is centered
    overlay_y: float = 0.75     # fraction of frame height where the overlay is centered
    overlay_scale: float = 0.35  # overlay width as a fraction of the frame width
    opacity: float = 1.0        # 0 (invisible) .. 1 (opaque)

    def __post_init__(self) -> None:
        self.validate()

    # ---- construction helpers -------------------------------------------
    @classmethod
    def from_video(cls, source: str, media_duration: float, **kwargs: Any) -> "Clip":
        kwargs.setdefault("src_out", media_duration)
        return cls(source=source, kind=KIND_VIDEO, media_duration=media_duration, **kwargs)

    @classmethod
    def from_audio(cls, source: str, media_duration: float, **kwargs: Any) -> "Clip":
        kwargs.setdefault("src_out", media_duration)
        return cls(source=source, kind=KIND_AUDIO, media_duration=media_duration, **kwargs)

    @classmethod
    def from_image(cls, source: str, duration: float = DEFAULT_IMAGE_DURATION,
                   **kwargs: Any) -> "Clip":
        return cls(source=source, kind=KIND_IMAGE, src_in=0.0, src_out=duration,
                   media_duration=None, **kwargs)

    @classmethod
    def from_title(cls, source: str, duration: float, text: str = "", style: str = "title",
                   background: str = "#101010", lines: Optional[List[List[str]]] = None,
                   **kwargs: Any) -> "Clip":
        """``source`` is the path to the already-rendered PNG card (see engine.titles)."""
        return cls(source=source, kind=KIND_TITLE, src_in=0.0, src_out=duration,
                   media_duration=None, text=text, text_style=style, text_background=background,
                   text_lines=lines, **kwargs)

    # ---- properties -----------------------------------------------------
    @property
    def duration(self) -> float:
        """Length on the timeline, taking speed into account."""
        return (self.src_out - self.src_in) / self.speed

    # ---- validation and editing -----------------------------------------
    def validate(self) -> None:
        if self.kind not in CLIP_KINDS:
            raise ValueError(f"Unknown clip kind: {self.kind!r}")
        if self.src_in < 0:
            raise ValueError("src_in must be >= 0")
        if self.src_out - self.src_in < MIN_SOURCE_LENGTH - _EPS:
            raise ValueError("Clip is too short (src_out must exceed src_in)")
        if self.media_duration is not None and self.src_out > self.media_duration + _EPS:
            raise ValueError("src_out is beyond the end of the source media")
        if not (MIN_SPEED <= self.speed <= MAX_SPEED):
            raise ValueError(f"speed must be between {MIN_SPEED} and {MAX_SPEED}")
        if not (0.0 <= self.volume <= MAX_VOLUME):
            raise ValueError(f"volume must be between 0 and {MAX_VOLUME}")
        if self.rotation not in VALID_ROTATIONS:
            raise ValueError("rotation must be 0, 90, 180 or 270")
        if not (-1.0 <= self.brightness <= 1.0):
            raise ValueError("brightness must be between -1 and 1")
        if self.fade_in < 0 or self.fade_out < 0:
            raise ValueError("fades must be >= 0")
        if self.start < 0:
            raise ValueError("start must be >= 0")
        if self.caption_position not in ("top", "middle", "bottom"):
            raise ValueError("caption_position must be 'top', 'middle' or 'bottom'")
        if self.text_style not in ("title", "credits"):
            raise ValueError("text_style must be 'title' or 'credits'")
        if not (0.0 <= self.overlay_x <= 1.0) or not (0.0 <= self.overlay_y <= 1.0):
            raise ValueError("overlay_x and overlay_y must be between 0 and 1")
        if not (0.05 <= self.overlay_scale <= 1.0):
            raise ValueError("overlay_scale must be between 0.05 and 1")
        if not (0.0 <= self.opacity <= 1.0):
            raise ValueError("opacity must be between 0 and 1")

    def update(self, **changes: Any) -> None:
        """Change fields atomically: if the result is invalid, nothing changes."""
        names = {f.name for f in fields(self)} - {"id"}
        unknown = set(changes) - names
        if unknown:
            raise AttributeError(f"Unknown or read-only clip fields: {sorted(unknown)}")
        old = {name: getattr(self, name) for name in changes}
        for name, value in changes.items():
            setattr(self, name, value)
        try:
            self.validate()
        except ValueError:
            for name, value in old.items():
                setattr(self, name, value)
            raise

    def trim(self, src_in: Optional[float] = None, src_out: Optional[float] = None) -> None:
        changes: Dict[str, Any] = {}
        if src_in is not None:
            changes["src_in"] = src_in
        if src_out is not None:
            changes["src_out"] = src_out
        self.update(**changes)

    def rotate(self, degrees: int) -> None:
        """Rotate by a multiple of 90 degrees (positive = clockwise)."""
        if degrees % 90 != 0:
            raise ValueError("Rotation must be a multiple of 90 degrees")
        self.update(rotation=(self.rotation + degrees) % 360)

    def duplicate(self) -> "Clip":
        """Independent copy with a new id (used for copy/paste and split)."""
        transition = Transition(**self.transition_in.to_dict()) if self.transition_in else None
        lines = [list(pair) for pair in self.text_lines] if self.text_lines else None
        return replace(self, id=new_id(), transition_in=transition, text_lines=lines)

    # ---- serialization --------------------------------------------------
    def to_dict(self, base_dir: Optional[str] = None) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            f.name: getattr(self, f.name) for f in fields(self) if f.name != "transition_in"
        }
        data["source"] = encode_path(self.source, base_dir)
        data["transition_in"] = self.transition_in.to_dict() if self.transition_in else None
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any], base_dir: Optional[str] = None) -> "Clip":
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}  # ignore unknown keys
        kwargs["source"] = decode_path(kwargs["source"], base_dir)
        transition = kwargs.pop("transition_in", None)
        return cls(transition_in=Transition.from_dict(transition) if transition else None,
                   **kwargs)
