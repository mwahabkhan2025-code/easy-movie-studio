"""Commands for the edits Phase 3 adds: add/remove/move/rotate/trim/split, and
changing the project's aspect ratio. Each stores just enough to undo itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from ..model import Clip, Project, Track, Transition


@dataclass
class AddClipsCommand:
    """Adds one or more clips starting at ``index``. Used by import and paste."""

    track: Track
    clips: List[Clip]
    index: int
    label: str = "Add"

    def do(self) -> None:
        index = self.index
        for clip in self.clips:
            self.track.add_clip(clip, index)
            index += 1

    def undo(self) -> None:
        for clip in self.clips:
            self.track.remove_clip(clip.id)


@dataclass
class RemoveClipsCommand:
    """Removes the given clips, remembering their positions so undo restores
    both the clips and their original order."""

    track: Track
    clip_ids: List[str]
    label: str = "Remove"
    _removed: List[Tuple[int, Clip]] = field(default_factory=list, init=False, repr=False)

    def do(self) -> None:
        pairs = sorted((self.track.index_of(cid), cid) for cid in self.clip_ids)
        self._removed = [(index, self.track.get_clip(cid)) for index, cid in pairs]
        for index, clip in sorted(self._removed, key=lambda p: -p[0]):
            self.track.remove_clip(clip.id)

    def undo(self) -> None:
        for index, clip in sorted(self._removed, key=lambda p: p[0]):
            self.track.add_clip(clip, min(index, len(self.track.clips)))


@dataclass
class MoveClipCommand:
    """Reorders one clip to ``new_index`` (as used by drag-to-reorder)."""

    track: Track
    clip_id: str
    new_index: int
    label: str = "Reorder"
    _old_index: int = field(init=False, default=-1)

    def do(self) -> None:
        self._old_index = self.track.index_of(self.clip_id)
        self.track.move_clip(self.clip_id, self.new_index)

    def undo(self) -> None:
        self.track.move_clip(self.clip_id, self._old_index)


@dataclass
class RotateClipsCommand:
    """Rotates a set of clips by the same amount (a multiple of 90 degrees)."""

    track: Track
    clip_ids: List[str]
    degrees: int
    label: str = "Rotate"

    def do(self) -> None:
        for clip_id in self.clip_ids:
            self.track.get_clip(clip_id).rotate(self.degrees)

    def undo(self) -> None:
        for clip_id in self.clip_ids:
            self.track.get_clip(clip_id).rotate(-self.degrees)


@dataclass
class TrimClipCommand:
    """Sets a clip's in/out points (used by Set start/end point and edge-dragging)."""

    track: Track
    clip_id: str
    new_in: float
    new_out: float
    label: str = "Trim"
    _old_in: float = field(init=False, default=0.0)
    _old_out: float = field(init=False, default=0.0)

    def do(self) -> None:
        clip = self.track.get_clip(self.clip_id)
        self._old_in, self._old_out = clip.src_in, clip.src_out
        clip.trim(src_in=self.new_in, src_out=self.new_out)

    def undo(self) -> None:
        self.track.get_clip(self.clip_id).trim(src_in=self._old_in, src_out=self._old_out)


@dataclass
class SplitClipCommand:
    """Splits a clip in two at timeline time ``at``. ``new_clip_id`` is set after do()
    runs, so the caller can select or otherwise use the new second half."""

    track: Track
    clip_id: str
    at: float
    label: str = "Split"
    new_clip_id: Optional[str] = field(init=False, default=None)
    _old_out: float = field(init=False, default=0.0)
    _old_fade_out: float = field(init=False, default=0.0)

    def do(self) -> None:
        clip = self.track.get_clip(self.clip_id)
        self._old_out = clip.src_out
        self._old_fade_out = clip.fade_out
        self.new_clip_id = self.track.split_clip(self.clip_id, self.at).id

    def undo(self) -> None:
        self.track.remove_clip(self.new_clip_id)
        self.track.get_clip(self.clip_id).update(src_out=self._old_out,
                                                  fade_out=self._old_fade_out)


@dataclass
class SetClipStartCommand:
    """Moves a clip on a non-ripple track (Music, Narration, an overlay video track) to a
    new start time -- the timeline-view equivalent of MoveClipCommand's reordering."""

    track: Track
    clip_id: str
    new_start: float
    label: str = "Move"
    _old_start: float = field(init=False, default=0.0)

    def do(self) -> None:
        clip = self.track.get_clip(self.clip_id)
        self._old_start = clip.start
        clip.update(start=self.new_start)

    def undo(self) -> None:
        self.track.get_clip(self.clip_id).update(start=self._old_start)


@dataclass
class SetOverlayCommand:
    """Sets picture-in-picture placement (position, scale, opacity) on a clip."""

    track: Track
    clip_id: str
    x: float
    y: float
    scale: float
    opacity: float
    label: str = "Picture-in-picture"
    _old: Tuple[float, float, float, float] = field(init=False, default=(0.0, 0.0, 0.0, 0.0))

    def do(self) -> None:
        clip = self.track.get_clip(self.clip_id)
        self._old = (clip.overlay_x, clip.overlay_y, clip.overlay_scale, clip.opacity)
        clip.update(overlay_x=self.x, overlay_y=self.y, overlay_scale=self.scale,
                   opacity=self.opacity)

    def undo(self) -> None:
        x, y, scale, opacity = self._old
        self.track.get_clip(self.clip_id).update(overlay_x=x, overlay_y=y, overlay_scale=scale,
                                                  opacity=opacity)


@dataclass
class SetAudioMixCommand:
    """Sets the project's overall music/video volume and the "duck music" flag."""

    project: Project
    music_volume: float
    video_volume: float
    duck_music: bool
    label: str = "Audio mix"
    _old: Tuple[float, float, bool] = field(init=False, default=(1.0, 1.0, False))

    def do(self) -> None:
        s = self.project.settings
        self._old = (s.music_volume, s.video_volume, s.duck_music)
        s.update(music_volume=self.music_volume, video_volume=self.video_volume,
                duck_music=self.duck_music)

    def undo(self) -> None:
        s = self.project.settings
        s.update(music_volume=self._old[0], video_volume=self._old[1], duck_music=self._old[2])


@dataclass
class SetAspectCommand:
    """Changes the project's aspect-ratio preset."""

    project: Project
    aspect_label: str
    label: str = "Aspect ratio"
    _old: Tuple[int, int] = field(init=False, default=(0, 0))

    def do(self) -> None:
        self._old = (self.project.settings.width, self.project.settings.height)
        self.project.set_aspect(self.aspect_label)

    def undo(self) -> None:
        self.project.settings.width, self.project.settings.height = self._old


@dataclass
class SetClipFieldCommand:
    """Sets one plain field (effect, pan_zoom, or brightness) on a set of clips."""

    track: Track
    clip_ids: List[str]
    field_name: str
    value: object
    label: str = "Change"
    _old: dict = field(default_factory=dict, init=False, repr=False)

    def do(self) -> None:
        self._old = {}
        for clip_id in self.clip_ids:
            clip = self.track.get_clip(clip_id)
            self._old[clip_id] = getattr(clip, self.field_name)
            clip.update(**{self.field_name: self.value})

    def undo(self) -> None:
        for clip_id, value in self._old.items():
            self.track.get_clip(clip_id).update(**{self.field_name: value})


@dataclass
class SetCaptionCommand:
    """Sets (or clears) a burned-in caption on a single clip."""

    track: Track
    clip_id: str
    text: str
    position: str
    label: str = "Caption"
    _old_text: str = field(init=False, default="")
    _old_position: str = field(init=False, default="bottom")

    def do(self) -> None:
        clip = self.track.get_clip(self.clip_id)
        self._old_text, self._old_position = clip.caption_text, clip.caption_position
        clip.update(caption_text=self.text, caption_position=self.position)

    def undo(self) -> None:
        self.track.get_clip(self.clip_id).update(caption_text=self._old_text,
                                                  caption_position=self._old_position)


@dataclass
class SetTransitionCommand:
    """Sets (or clears, when ``name`` is None) the incoming transition on a set of clips."""

    track: Track
    clip_ids: List[str]
    name: Optional[str]
    duration: float
    label: str = "Transition"
    _old: dict = field(default_factory=dict, init=False, repr=False)

    def do(self) -> None:
        self._old = {}
        new_value = Transition(self.name, self.duration) if self.name else None
        for clip_id in self.clip_ids:
            clip = self.track.get_clip(clip_id)
            self._old[clip_id] = clip.transition_in
            clip.update(transition_in=new_value)

    def undo(self) -> None:
        for clip_id, value in self._old.items():
            self.track.get_clip(clip_id).update(transition_in=value)
