"""Low-resolution "proxy" copies of heavy video clips, used only to make preview
playback smoother on footage the machine struggles to decode live (large frame
sizes, heavy codecs). Export never touches a proxy -- ``build_export_plan`` always
reads each clip's own ``source`` file, so turning proxies on or off, or regenerating
them, can never change what gets exported.

Cached by content fingerprint (resolved path + size + modified time + target width),
the same pattern ``engine/titles.py`` uses for rendered title cards, so reopening a
project with the same footage reuses existing proxies instead of rebuilding them.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from ..model.clip import KIND_VIDEO, Clip
from ..model.project import Project, ProjectSettings
from ..model.track import TRACK_AUDIO, TRACK_VIDEO, Track
from .export_plan import ExportPlan, ExportSettings, build_export_plan, even
from .media_info import MediaInfo

CACHE_DIR = os.path.join(tempfile.gettempdir(), "mmclone_proxies")
PROXY_WIDTH = 640             # proxy target width; height keeps the source's aspect ratio
PROXY_MIN_SOURCE_WIDTH = 960  # a clip already narrower than this plays smoothly -- skip it


class ProxyError(Exception):
    """The proxy for this source can't be built."""


def _fingerprint(source_path: str) -> str:
    stat = os.stat(source_path)
    payload = {"path": os.path.realpath(source_path), "size": stat.st_size,
              "mtime": round(stat.st_mtime, 3), "width": PROXY_WIDTH}
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def proxy_path_for(source_path: str) -> str:
    """Where this source's proxy lives (or would live once built)."""
    return os.path.join(CACHE_DIR, f"{_fingerprint(source_path)}.mp4")


def proxy_ready(source_path: str) -> bool:
    try:
        path = proxy_path_for(source_path)
    except OSError:
        # The source has moved or been deleted since it was added to the project -- not
        # this function's problem to report, just nothing to resolve to.
        return False
    return os.path.isfile(path) and os.path.getsize(path) > 0


def needs_proxy(info: MediaInfo, min_width: int = PROXY_MIN_SOURCE_WIDTH) -> bool:
    """Whether this source is heavy enough that a proxy is worth generating at all.

    ``min_width`` defaults to the module constant but can be overridden (e.g. from the
    user's Options dialog) without touching the module-level default used elsewhere."""
    if info.kind != KIND_VIDEO or info.video is None:
        return False
    width = info.video.display_size[0]
    return width >= min_width


def build_proxy_plan(source_path: str, info: MediaInfo) -> ExportPlan:
    """A small, fast-encoded, full-length copy of ``source_path`` for preview only."""
    if info.video is None:
        raise ProxyError(f"{source_path!r} has no video stream to make a proxy of.")
    duration = info.duration or 0.0
    if duration <= 0:
        raise ProxyError(f"Couldn't determine the length of {source_path!r}.")

    src_width, src_height = info.video.display_size
    scale = (PROXY_WIDTH / src_width) if src_width else 1.0
    width, height = even(PROXY_WIDTH), even((src_height or 360) * scale)
    fps = info.video.fps or 30.0
    sample_rate = info.audio.sample_rate if info.audio and info.audio.sample_rate else 48000

    settings = ProjectSettings(width=width, height=height, fps=fps, sample_rate=sample_rate)
    project = Project(name="", settings=settings)
    clip = Clip(source=source_path, kind=KIND_VIDEO, src_in=0.0, src_out=duration,
               media_duration=duration)
    track = Track(kind=TRACK_VIDEO, name="Main", ripple=True)
    track.clips.append(clip)
    project.tracks.append(track)
    project.tracks.append(Track(kind=TRACK_AUDIO, name="Music", ripple=False))

    os.makedirs(CACHE_DIR, exist_ok=True)
    out_path = proxy_path_for(source_path)
    export_settings = ExportSettings(width=width, height=height, fps=fps,
                                     sample_rate=sample_rate, output_kind="video",
                                     video_codec="libx264", crf=28, speed_preset="ultrafast",
                                     audio_codec="aac", audio_bitrate="96k")
    return build_export_plan(project, out_path, export_settings)


class ProxyResolver:
    """What the preview player asks before opening a clip's source file: if proxies are
    turned on and a ready proxy exists for this source, play that instead. Export never
    uses this -- it only ever reads from export_plan.build_export_plan(project, ...)."""

    def __init__(self) -> None:
        self.enabled = False

    def resolve(self, source_path: str) -> str:
        if not self.enabled:
            return source_path
        if proxy_ready(source_path):
            return proxy_path_for(source_path)
        return source_path
