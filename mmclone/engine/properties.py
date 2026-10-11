"""Turns a MediaInfo (and optionally a Clip) into readable rows for the Properties dialog."""

from __future__ import annotations

import math
import os
from datetime import datetime
from typing import List, Optional, Tuple

from ..model import Clip, ProjectSettings
from ..model.clip import KIND_IMAGE, KIND_VIDEO
from ..util import format_time
from .media_info import MediaInfo

Row = Tuple[str, str]
Section = Tuple[str, List[Row]]

_CONTAINERS = (("mp4", "MP4"), ("matroska", "Matroska (MKV/WebM)"), ("avi", "AVI"),
               ("asf", "Windows Media (ASF/WMV)"), ("mpegts", "MPEG-TS"), ("flv", "Flash Video"),
               ("mpeg", "MPEG"), ("image2", "Image"), ("wav", "WAV"), ("mp3", "MP3"),
               ("flac", "FLAC"), ("ogg", "Ogg"), ("gif", "GIF"), ("webp_pipe", "WebP"))
_HIDDEN_METADATA = {"major_brand", "minor_version", "compatible_brands", "handler_name",
                    "vendor_id"}


def format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} bytes" if unit == "bytes" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{num_bytes} bytes"  # unreachable


def format_bitrate(bits_per_second: Optional[int]) -> str:
    if not bits_per_second:
        return "Unknown"
    if bits_per_second >= 1_000_000:
        return f"{bits_per_second / 1_000_000:.2f} Mbps"
    return f"{round(bits_per_second / 1000)} kbps"


def aspect_text(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return ""
    divisor = math.gcd(width, height)
    w, h = width // divisor, height // divisor
    if w > 32 or h > 32:
        return f"{width / height:.2f}:1"
    return f"{w}:{h}"


def container_label(name: str) -> str:
    lowered = name.lower()
    for key, label in _CONTAINERS:
        if key in lowered:
            return label
    return name or "Unknown"


def channel_label(channels: Optional[int], layout: Optional[str]) -> str:
    names = {1: "Mono", 2: "Stereo", 6: "5.1 surround", 8: "7.1 surround"}
    if channels in names:
        return names[channels]
    return layout or (f"{channels} channels" if channels else "Unknown")


def _fps_text(fps: Optional[float]) -> str:
    if not fps:
        return "Unknown"
    return f"{fps:.3f}".rstrip("0").rstrip(".") + " fps"


def _split_path(path: str) -> Tuple[str, str]:
    return os.path.basename(path), os.path.dirname(path)


def describe(info: MediaInfo, clip: Optional[Clip] = None) -> List[Section]:
    name, folder = _split_path(info.path)
    general: List[Row] = [
        ("Name", name), ("Location", folder), ("Size", format_size(info.size_bytes)),
        ("Format", container_label(info.container)),
    ]
    if info.duration:
        general.append(("Duration", format_time(info.duration)))
    if info.bitrate:
        general.append(("Overall bitrate", format_bitrate(info.bitrate)))
    if info.modified:
        general.append(("Modified", datetime.fromtimestamp(info.modified).strftime("%Y-%m-%d %H:%M")))
    sections: List[Section] = [("General", general)]

    if info.video is not None:
        v = info.video
        codec = v.codec + (f" ({v.profile})" if v.profile else "")
        w, h = v.display_size
        rows: List[Row] = [("Codec", codec), ("Resolution", f"{w} \u00d7 {h}  ({aspect_text(w, h)})")]
        if info.kind == KIND_VIDEO:
            rows.append(("Frame rate", _fps_text(v.fps)))
            rows.append(("Video bitrate", format_bitrate(v.bitrate)))
        if v.pix_fmt:
            rows.append(("Pixel format", v.pix_fmt))
        if v.rotation:
            rows.append(("Rotation flag", f"{v.rotation}\u00b0 (applied automatically)"))
        sections.append(("Video" if info.kind == KIND_VIDEO else "Photo", rows))

    if info.kind == KIND_VIDEO or info.audio is not None:
        if info.audio is not None:
            a = info.audio
            sections.append(("Audio", [
                ("Codec", a.codec + (f" ({a.profile})" if a.profile else "")),
                ("Sample rate", f"{a.sample_rate / 1000:.1f} kHz" if a.sample_rate else "Unknown"),
                ("Channels", channel_label(a.channels, a.channel_layout)),
                ("Audio bitrate", format_bitrate(a.bitrate)),
            ]))
        else:
            sections.append(("Audio", [("Audio", "This file has no audio")]))

    if info.kind == KIND_VIDEO and (info.video_streams > 1 or info.audio_streams > 1
                                    or info.subtitle_streams):
        sections.append(("Streams", [("Video streams", str(info.video_streams)),
                                     ("Audio streams", str(info.audio_streams)),
                                     ("Subtitle streams", str(info.subtitle_streams))]))

    # A few tag names collide with labels already used above (e.g. a GPS "location"
    # tag vs. the file's folder "Location"); rename those instead of showing duplicates.
    _RENAME = {"location": "GPS coordinates", "com.apple.quicktime.location.iso6709":
               "GPS coordinates"}
    meta = [(_RENAME.get(k, k.replace("_", " ").capitalize()), v)
            for k, v in info.metadata.items() if k not in _HIDDEN_METADATA and v]
    if meta:
        sections.append(("Details", meta))

    if clip is not None:
        rows = []
        if clip.kind != KIND_IMAGE:
            rows += [("Starts at", format_time(clip.src_in)), ("Ends at", format_time(clip.src_out))]
        rows.append(("Length in movie", format_time(clip.duration)))
        rows.append(("Speed", f"{clip.speed:g}x"))
        if clip.kind != KIND_IMAGE:
            rows.append(("Volume", f"{round(clip.volume * 100)}%"))
        rows.append(("Rotation", f"{clip.rotation}\u00b0"))
        if clip.effect:
            rows.append(("Effect", clip.effect))
        if clip.transition_in:
            rows.append(("Transition in", f"{clip.transition_in.name} ({clip.transition_in.duration:g} s)"))
        sections.append(("In this movie", rows))
    return sections


def compare_with_project(info: MediaInfo, settings: ProjectSettings) -> List[str]:
    """Human-readable notes about how this file differs from the project settings."""
    notes: List[str] = []
    if info.video is not None:
        w, h = info.video.display_size
        if (w, h) != (settings.width, settings.height):
            same_shape = abs(w / h - settings.width / settings.height) < 0.02 if h else False
            how = "it will be scaled to fit" if same_shape else \
                "it will be scaled and shown with black bars"
            notes.append(f"Size {w}\u00d7{h} differs from the project "
                         f"({settings.width}\u00d7{settings.height}); {how}.")
        if info.kind == KIND_VIDEO and info.video.fps and abs(info.video.fps - settings.fps) > 0.5:
            notes.append(f"Frame rate {_fps_text(info.video.fps)} differs from the project "
                         f"({settings.fps:g} fps); frames will be converted.")
        if info.video.rotation:
            notes.append(f"This file is rotated {info.video.rotation}\u00b0 by a flag; "
                         f"it is turned upright automatically.")
    if info.kind == KIND_VIDEO and not info.has_audio:
        notes.append("This video has no audio.")
    return notes


def sections_to_text(sections: List[Section], notes: Optional[List[str]] = None) -> str:
    lines: List[str] = []
    for note in notes or []:
        lines.append(f"! {note}")
    if lines:
        lines.append("")
    for title, rows in sections:
        lines.append(title)
        lines.extend(f"  {label}: {value}" for label, value in rows)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
