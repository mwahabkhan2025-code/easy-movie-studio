"""Stand-alone file operations: Compress/Convert a video, and Extract audio from one.

These don't touch the storyboard at all -- the person picks any file on disk and gets
back a re-encoded (or audio-only) copy of it. Rather than duplicating FFmpeg command
construction, each builder wraps the target file in a throwaway, one-clip Project and
hands it to the exact same, already-tested ``build_export_plan``/``resolve_settings``
pipeline the real export dialog uses. That means compression inherits every fix made
there (silence handling, even dimensions, codec/container choices) for free, and any
future export-side fix applies here too without a second code path to maintain.
"""

from __future__ import annotations

from typing import Optional

from ..model.clip import Clip, KIND_AUDIO, KIND_VIDEO
from ..model.project import Project, ProjectSettings
from ..model.track import TRACK_AUDIO, TRACK_VIDEO, Track
from .export_plan import ExportError, ExportPlan, ExportSettings, PRESETS, build_export_plan, even
from .media_info import MediaInfo
from .probe import probe as probe_media

COMPRESS_PRESETS = {k: v for k, v in PRESETS.items() if v.output_kind == "video"}


def _project_for_file(input_path: str, info: MediaInfo) -> Project:
    """A one-clip, one-track project whose only job is to carry ``input_path`` through
    the export pipeline. Width/height come from the probed video stream (falling back to
    a safe default for an audio file being wrapped only to reuse the audio-export path)."""
    if info.video is not None:
        width, height = info.video.display_size
        width, height = even(width or 1920), even(height or 1080)
    else:
        width, height = 1920, 1080
    duration = info.duration or 0.0
    if duration <= 0:
        raise ExportError(f"Couldn't determine the length of {input_path!r}.")

    settings = ProjectSettings(width=width, height=height,
                               fps=(info.video.fps if info.video and info.video.fps else 30.0),
                               sample_rate=(info.audio.sample_rate
                                           if info.audio and info.audio.sample_rate else 48000))
    project = Project(name="", settings=settings)
    kind = KIND_VIDEO if info.kind != "audio" else KIND_AUDIO
    clip = Clip(source=input_path, kind=kind, src_in=0.0, src_out=duration,
               media_duration=duration)
    # The "main track" the export pipeline looks for is always project.video_tracks()[0],
    # whatever kind of clip actually sits on it -- Track.layout()/export don't care, only
    # Track.add_clip()'s own validation does, which this internal, throwaway project never
    # goes through. Keeping it TRACK_VIDEO (even for a wrapped audio file, extracting its
    # own audio) means Project.main_track always resolves.
    track = Track(kind=TRACK_VIDEO, name="Main", ripple=True)
    track.clips.append(clip)
    project.tracks.append(track)
    project.tracks.append(Track(kind=TRACK_AUDIO, name="Music", ripple=False))
    return project


def build_compress_plan(input_path: str, output_path: str, preset_id: str = "recommended",
                        crf: Optional[int] = None, speed_preset: Optional[str] = None,
                        info: Optional[MediaInfo] = None) -> ExportPlan:
    """Re-encode (compress or convert) a single video file.

    ``preset_id`` picks a starting point from the same preset table the export dialog
    uses (any entry whose output is a video, e.g. "recommended", "hq", "standard",
    "small", "mobile", "youtube", "vertical"); ``crf``/``speed_preset`` optionally
    override that preset's quality/speed for finer control. The container is taken from
    ``output_path``'s own extension, so "Convert format" (e.g. .mov -> .mp4) is just a
    compress with the recommended preset and a different output name.
    """
    if preset_id not in COMPRESS_PRESETS:
        raise ValueError(f"Unknown compress preset: {preset_id!r}")
    info = info or probe_media(input_path)
    if info.kind == "audio":
        raise ExportError("That file has no video stream to compress -- "
                          "use Extract Audio instead.")
    project = _project_for_file(input_path, info)
    settings = resolve_compress_settings(project, preset_id, crf=crf, speed_preset=speed_preset)
    return build_export_plan(project, output_path, settings)


def resolve_compress_settings(project: Project, preset_id: str, crf: Optional[int] = None,
                              speed_preset: Optional[str] = None) -> ExportSettings:
    from .export_plan import resolve_settings
    settings = resolve_settings(project, preset_id)
    if crf is not None:
        settings.crf = crf
    if speed_preset is not None:
        settings.speed_preset = speed_preset
    return settings


def build_extract_audio_plan(input_path: str, output_path: str, audio_bitrate: str = "192k",
                             info: Optional[MediaInfo] = None) -> ExportPlan:
    """Pull just the audio out of a video (or re-encode an audio file to a new bitrate),
    reusing the audio-export branch of ``build_export_plan``."""
    info = info or probe_media(input_path)
    if not info.has_audio:
        raise ExportError(f"{input_path!r} doesn't have an audio track to extract.")
    project = _project_for_file(input_path, info)
    settings = resolve_settings_for_audio(project, audio_bitrate)
    return build_export_plan(project, output_path, settings)


def resolve_settings_for_audio(project: Project, audio_bitrate: str) -> ExportSettings:
    from .export_plan import resolve_settings
    settings = resolve_settings(project, "audio")
    settings.audio_bitrate = audio_bitrate
    return settings
