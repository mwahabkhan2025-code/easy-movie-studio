"""Project: settings + tracks, with JSON save/load."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .clip import Clip
from .track import TRACK_AUDIO, TRACK_VIDEO, Track

FORMAT_VERSION = 1
PROJECT_EXTENSION = ".mmproj"

ASPECT_PRESETS: Dict[str, Tuple[int, int]] = {
    "16:9": (1920, 1080),
    "4:3": (1440, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
}


class ProjectFormatError(Exception):
    """Raised when a project file cannot be read."""


@dataclass
class ProjectSettings:
    width: int = 1920
    height: int = 1080
    fps: float = 30.0
    sample_rate: int = 48000
    music_volume: float = 1.0    # overall multiplier on every Music-track clip's own volume
    video_volume: float = 1.0    # overall multiplier on every main-track clip's own volume
    duck_music: bool = False     # automatically lower music_volume where the video has audio

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if self.width <= 0 or self.height <= 0 or self.fps <= 0 or self.sample_rate <= 0:
            raise ValueError("Project settings must be positive")
        if not (0.0 <= self.music_volume <= 2.0) or not (0.0 <= self.video_volume <= 2.0):
            raise ValueError("music_volume and video_volume must be between 0 and 2")

    def update(self, **changes: Any) -> None:
        """Change fields atomically: if the result is invalid, nothing changes.

        Direct attribute assignment (``settings.music_volume = 5.0``) skips validation
        entirely, since a dataclass only validates in __post_init__; use this instead
        for any change that didn't just come from the constructor.
        """
        old = {name: getattr(self, name) for name in changes}
        for name, value in changes.items():
            setattr(self, name, value)
        try:
            self.validate()
        except ValueError:
            for name, value in old.items():
                setattr(self, name, value)
            raise

    @property
    def aspect_label(self) -> str:
        for label, size in ASPECT_PRESETS.items():
            if size == (self.width, self.height):
                return label
        return "custom"

    def to_dict(self) -> Dict[str, Any]:
        return {"width": self.width, "height": self.height, "fps": self.fps,
                "sample_rate": self.sample_rate, "music_volume": self.music_volume,
                "video_volume": self.video_volume, "duck_music": self.duck_music}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectSettings":
        return cls(width=int(data.get("width", 1920)), height=int(data.get("height", 1080)),
                   fps=float(data.get("fps", 30.0)),
                   sample_rate=int(data.get("sample_rate", 48000)),
                   music_volume=float(data.get("music_volume", 1.0)),
                   video_volume=float(data.get("video_volume", 1.0)),
                   duck_music=bool(data.get("duck_music", False)))


@dataclass
class Project:
    name: str = "My Movie"
    settings: ProjectSettings = field(default_factory=ProjectSettings)
    tracks: List[Track] = field(default_factory=list)

    @classmethod
    def new(cls, name: str = "My Movie") -> "Project":
        """A fresh project: one video/photo track and one music track."""
        project = cls(name=name)
        project.tracks.append(Track(kind=TRACK_VIDEO, name="Video", ripple=True))
        project.tracks.append(Track(kind=TRACK_AUDIO, name="Music", ripple=False))
        return project

    # ---- tracks and clips -------------------------------------------------
    def add_track(self, kind: str, name: str = "", ripple: Optional[bool] = None) -> Track:
        if ripple is None:
            ripple = kind == TRACK_VIDEO and not self.video_tracks()
        track = Track(kind=kind, name=name or f"{kind.title()} {len(self.tracks) + 1}",
                      ripple=ripple)
        self.tracks.append(track)
        return track

    def remove_track(self, track_id: str) -> Track:
        track = self.get_track(track_id)
        if track.kind == TRACK_VIDEO and len(self.video_tracks()) == 1:
            raise ValueError("A project needs at least one video track")
        self.tracks.remove(track)
        return track

    def get_track(self, track_id: str) -> Track:
        for track in self.tracks:
            if track.id == track_id:
                return track
        raise KeyError(track_id)

    def video_tracks(self) -> List[Track]:
        return [t for t in self.tracks if t.kind == TRACK_VIDEO]

    @property
    def main_track(self) -> Track:
        """The first video track (the storyboard)."""
        tracks = self.video_tracks()
        if not tracks:
            raise ValueError("Project has no video track")
        return tracks[0]

    def find_clip(self, clip_id: str) -> Tuple[Track, Clip]:
        for track in self.tracks:
            for clip in track.clips:
                if clip.id == clip_id:
                    return track, clip
        raise KeyError(clip_id)

    @property
    def duration(self) -> float:
        return max((t.duration for t in self.tracks), default=0.0)

    def set_aspect(self, label: str) -> None:
        if label not in ASPECT_PRESETS:
            raise ValueError(f"Unknown aspect ratio: {label!r}")
        self.settings.width, self.settings.height = ASPECT_PRESETS[label]

    # ---- serialization ----------------------------------------------------
    def to_dict(self, base_dir: Optional[str] = None) -> Dict[str, Any]:
        return {
            "format_version": FORMAT_VERSION,
            "name": self.name,
            "settings": self.settings.to_dict(),
            "tracks": [t.to_dict(base_dir) for t in self.tracks],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], base_dir: Optional[str] = None) -> "Project":
        if not isinstance(data, dict) or "format_version" not in data:
            raise ProjectFormatError("Not a valid project file")
        version = data["format_version"]
        if not isinstance(version, int) or version > FORMAT_VERSION:
            raise ProjectFormatError(
                f"Project was saved by a newer version (format {version}); "
                f"this version reads up to format {FORMAT_VERSION}")
        try:
            return cls(
                name=data.get("name", "My Movie"),
                settings=ProjectSettings.from_dict(data.get("settings", {})),
                tracks=[Track.from_dict(t, base_dir) for t in data.get("tracks", [])],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProjectFormatError(f"Project file is damaged: {exc}") from exc

    def save(self, path: str) -> None:
        """Write the project as JSON. Media paths are stored relative to the file.

        The file is written to a temporary name first and then swapped in, so
        a crash mid-save never destroys the previous version.
        """
        path = os.path.abspath(path)
        base_dir = os.path.dirname(path)
        payload = json.dumps(self.to_dict(base_dir), indent=2, ensure_ascii=False)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_path, path)

    @classmethod
    def load(cls, path: str) -> "Project":
        path = os.path.abspath(path)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ProjectFormatError(f"Project file is not valid JSON: {exc}") from exc
        return cls.from_dict(data, os.path.dirname(path))
