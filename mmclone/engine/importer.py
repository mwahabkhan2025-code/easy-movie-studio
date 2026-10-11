"""Turning chosen files into clips, and choosing project settings from the first clip."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from ..model import ASPECT_PRESETS, Clip, Track
from ..model.clip import KIND_AUDIO, KIND_IMAGE, KIND_VIDEO
from .media_info import MediaInfo
from .probe import IMAGE_EXTS, VIDEO_EXTS, ProbeError, probe

COMMON_FPS = (24.0, 25.0, 30.0, 50.0, 60.0)


@dataclass
class ImportResult:
    clips: List[Clip] = field(default_factory=list)
    infos: Dict[str, MediaInfo] = field(default_factory=dict)
    errors: List[Tuple[str, str]] = field(default_factory=list)  # (path, reason)


def clip_from_info(info: MediaInfo) -> Clip:
    if info.kind == KIND_VIDEO:
        return Clip.from_video(info.path, info.duration or 0.0)
    if info.kind == KIND_IMAGE:
        return Clip.from_image(info.path)
    return Clip.from_audio(info.path, info.duration or 0.0)


def import_media(paths: Sequence[str],
                 allowed_kinds: Sequence[str] = (KIND_VIDEO, KIND_IMAGE)) -> ImportResult:
    """Probe each file and build a clip for it. Bad files are reported, not fatal."""
    result = ImportResult()
    for path in paths:
        try:
            info = probe(path)
        except ProbeError as exc:
            result.errors.append((path, str(exc)))
            continue
        if info.kind not in allowed_kinds:
            reason = ("Audio files are added with Add music" if info.kind == KIND_AUDIO
                      else "This kind of file can't be added here")
            result.errors.append((path, reason))
            continue
        result.infos[path] = info
        result.clips.append(clip_from_info(info))
    return result


def scan_media(paths: Sequence[str]) -> Tuple[Dict[str, MediaInfo], Dict[str, str]]:
    """Probe existing project media. Returns (infos, problems) keyed by path."""
    infos: Dict[str, MediaInfo] = {}
    problems: Dict[str, str] = {}
    for path in dict.fromkeys(paths):  # unique, keep order
        try:
            infos[path] = probe(path)
        except ProbeError as exc:
            problems[path] = str(exc)
    return infos, problems


def insert_position(track: Track, selected_ids: Sequence[str]) -> int:
    """Where new clips go: after the last selected clip, otherwise at the end."""
    if not selected_ids:
        return len(track.clips)
    indexes = [i for i, clip in enumerate(track.clips) if clip.id in selected_ids]
    return max(indexes) + 1 if indexes else len(track.clips)


def nearest_aspect(width: int, height: int) -> str:
    """The aspect-ratio preset closest to width:height."""
    if width <= 0 or height <= 0:
        return "16:9"
    target = math.log(width / height)
    return min(ASPECT_PRESETS,
               key=lambda label: abs(math.log(ASPECT_PRESETS[label][0] / ASPECT_PRESETS[label][1])
                                     - target))


def nearest_fps(fps: Optional[float], default: float = 30.0) -> float:
    """Snap to a common frame rate (29.97 -> 30); keep ``default`` if nothing is close."""
    if not fps:
        return default
    best = min(COMMON_FPS, key=lambda candidate: abs(candidate - fps))
    return best if abs(best - fps) <= 1.5 else default


def suggest_settings(info: MediaInfo) -> Tuple[str, Optional[float]]:
    """(aspect label, fps or None) suggested by the first clip added to a project."""
    if info.video is None:
        return "16:9", None
    width, height = info.video.display_size
    fps = nearest_fps(info.video.fps) if info.kind == KIND_VIDEO and info.video.fps else None
    return nearest_aspect(width, height), fps


def display_name(path: str) -> str:
    return os.path.basename(path) or path


def expand_paths(paths: Sequence[str]) -> List[str]:
    """Files stay as they are; a dropped folder becomes the videos and photos inside it."""
    expanded: List[str] = []
    for path in paths:
        if os.path.isdir(path):
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                if os.path.isfile(full) and name.lower().endswith(VIDEO_EXTS + IMAGE_EXTS):
                    expanded.append(full)
        elif path:
            expanded.append(path)
    return expanded
