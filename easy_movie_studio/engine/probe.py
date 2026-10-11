"""Read media properties with ffprobe, or by parsing ``ffmpeg -i`` when ffprobe is absent."""

from __future__ import annotations

import json
import math
import os
import re
from typing import Any, Dict, Optional

from ..model.clip import KIND_AUDIO, KIND_IMAGE, KIND_VIDEO
from .media_info import AudioStream, MediaInfo, VideoStream
from .tools import find_ffmpeg, find_ffprobe, run_tool

VIDEO_EXTS = (".mp4", ".m4v", ".mov", ".mkv", ".avi", ".wmv", ".webm", ".mpg", ".mpeg",
              ".mts", ".m2ts", ".3gp", ".flv", ".ts", ".asf")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp")
AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".wma", ".flac", ".ogg", ".opus")


class ProbeError(Exception):
    """The file is missing, unreadable, or not a supported media file."""


def classify(path: str) -> Optional[str]:
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXTS:
        return KIND_VIDEO
    if ext in IMAGE_EXTS:
        return KIND_IMAGE
    if ext in AUDIO_EXTS:
        return KIND_AUDIO
    return None


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _ratio(text: Any) -> Optional[float]:
    if not isinstance(text, str) or "/" not in text:
        return _to_float(text)
    num, _, den = text.partition("/")
    n, d = _to_float(num), _to_float(den)
    if n is None or not d:
        return None
    return n / d if n > 0 else None


def _normalize_rotation(degrees: float) -> int:
    return (int(round(degrees / 90.0)) * 90) % 360


# ---------------------------------------------------------------------------
# ffprobe JSON
# ---------------------------------------------------------------------------
def parse_ffprobe_json(data: Dict[str, Any], path: str) -> MediaInfo:
    fmt = data.get("format") or {}
    info = MediaInfo(path=path, kind=classify(path) or KIND_VIDEO,
                     container=str(fmt.get("format_name", "")),
                     duration=_to_float(fmt.get("duration")),
                     bitrate=_to_int(fmt.get("bit_rate")),
                     metadata={str(k).lower(): str(v) for k, v in (fmt.get("tags") or {}).items()})
    for stream in data.get("streams") or []:
        ctype = stream.get("codec_type")
        if ctype == "video":
            if (stream.get("disposition") or {}).get("attached_pic"):
                continue  # album art in an audio file
            info.video_streams += 1
            if info.video is None:
                rotation = 0
                for side in stream.get("side_data_list") or []:
                    if "rotation" in side:
                        rotation = _normalize_rotation(-float(side["rotation"]))
                if not rotation:
                    tag = (stream.get("tags") or {}).get("rotate")
                    if tag is not None and _to_float(tag) is not None:
                        rotation = _normalize_rotation(float(tag))
                info.video = VideoStream(
                    codec=str(stream.get("codec_name", "")),
                    profile=stream.get("profile"),
                    width=_to_int(stream.get("width")) or 0,
                    height=_to_int(stream.get("height")) or 0,
                    fps=_ratio(stream.get("avg_frame_rate")) or _ratio(stream.get("r_frame_rate")),
                    bitrate=_to_int(stream.get("bit_rate")),
                    pix_fmt=stream.get("pix_fmt"),
                    rotation=rotation)
        elif ctype == "audio":
            info.audio_streams += 1
            if info.audio is None:
                info.audio = AudioStream(
                    codec=str(stream.get("codec_name", "")),
                    profile=stream.get("profile"),
                    sample_rate=_to_int(stream.get("sample_rate")),
                    channels=_to_int(stream.get("channels")),
                    channel_layout=stream.get("channel_layout"),
                    bitrate=_to_int(stream.get("bit_rate")))
        elif ctype == "subtitle":
            info.subtitle_streams += 1
    return info


# ---------------------------------------------------------------------------
# Fallback: parse the text printed by `ffmpeg -i file`
# ---------------------------------------------------------------------------
_STREAM = re.compile(r"Stream #0:(\d+)(?:\[[^\]]*\])?(?:\([^)]*\))?: (\w+): (.*)$")
_LAYOUT_CHANNELS = {"mono": 1, "stereo": 2, "quad": 4, "downmix": 2}


def _strip_parens(text: str) -> str:
    return re.sub(r"\([^()]*\)", "", text)


def _profile(rest: str) -> Optional[str]:
    match = re.match(r"^\w+ \(([A-Za-z][^)/]*?)\)", rest)
    return match.group(1) if match else None


def _channels(layout: str) -> Optional[int]:
    layout = layout.strip()
    if layout in _LAYOUT_CHANNELS:
        return _LAYOUT_CHANNELS[layout]
    match = re.match(r"^(\d+)\.(\d+)", layout)
    if match:
        return int(match.group(1)) + int(match.group(2))
    match = re.match(r"^(\d+) channels", layout)
    return int(match.group(1)) if match else None


def parse_ffmpeg_info(text: str, path: str) -> MediaInfo:
    """Parse ``ffmpeg -i`` output. Raises ProbeError if it does not describe a media file."""
    lines = text.splitlines()
    container = re.search(r"Input #0,\s*(.+?),\s*from\s", text)
    if not container:
        reason = next((ln.strip() for ln in lines if re.search(
            r"No such file|Invalid data|moov atom|Permission denied|Is a directory|"
            r"could not find codec", ln)), "Unrecognized media file")
        raise ProbeError(reason)

    info = MediaInfo(path=path, kind=classify(path) or KIND_VIDEO, container=container.group(1))
    duration = re.search(r"Duration:\s*(\d+):(\d\d):(\d\d(?:\.\d+)?)", text)
    if duration:
        h, m, s = duration.groups()
        info.duration = int(h) * 3600 + int(m) * 60 + float(s)
    bitrate = re.search(r"Duration:.*?bitrate:\s*(\d+)\s*kb/s", text)
    if bitrate:
        info.bitrate = int(bitrate.group(1)) * 1000

    in_top_metadata = False
    last_video: Optional[VideoStream] = None
    for line in lines:
        if line.startswith("  Metadata:"):
            in_top_metadata = True
            continue
        if line.startswith("  Duration:"):
            in_top_metadata = False
        if in_top_metadata:
            meta = re.match(r"^ {4}(\S[^:]*?)\s*:\s(.*)$", line)
            if meta:
                info.metadata[meta.group(1).strip().lower()] = meta.group(2).strip()
            continue
        stream = _STREAM.search(line)
        if stream:
            ctype, rest = stream.group(2), stream.group(3)
            stripped = _strip_parens(rest)
            tokens = [t.strip() for t in stripped.split(",")]
            if ctype == "Video":
                if "(attached pic)" in rest:
                    last_video = None
                    continue
                info.video_streams += 1
                if info.video is None:
                    size = re.search(r"\b(\d{2,5})x(\d{2,5})\b", stripped)
                    fps = re.search(r"([\d.]+) fps", stripped)
                    kbps = re.search(r"(\d+) kb/s", stripped)
                    pix = tokens[1] if len(tokens) > 1 and re.fullmatch(r"[a-z][a-z0-9_]*", tokens[1]) else None
                    info.video = VideoStream(
                        codec=tokens[0].split()[0] if tokens and tokens[0] else "",
                        profile=_profile(rest),
                        width=int(size.group(1)) if size else 0,
                        height=int(size.group(2)) if size else 0,
                        fps=float(fps.group(1)) if fps else None,
                        bitrate=int(kbps.group(1)) * 1000 if kbps else None,
                        pix_fmt=pix)
                    last_video = info.video
            elif ctype == "Audio":
                info.audio_streams += 1
                if info.audio is None:
                    hz = re.search(r"(\d+) Hz", stripped)
                    kbps = re.search(r"(\d+) kb/s", stripped)
                    layout = ""
                    for i, token in enumerate(tokens):
                        if token.endswith("Hz") and i + 1 < len(tokens):
                            layout = tokens[i + 1]
                            break
                    info.audio = AudioStream(
                        codec=tokens[0].split()[0] if tokens and tokens[0] else "",
                        profile=_profile(rest),
                        sample_rate=int(hz.group(1)) if hz else None,
                        channels=_channels(layout),
                        channel_layout=layout or None,
                        bitrate=int(kbps.group(1)) * 1000 if kbps else None)
            elif ctype == "Subtitle":
                info.subtitle_streams += 1
            continue
        if last_video is not None:
            rot = re.search(r"rotation of (-?[\d.]+) degrees", line)
            if rot:
                last_video.rotation = _normalize_rotation(-float(rot.group(1)))
                continue
            old = re.match(r"^\s{6}rotate\s*:\s*(\d+)\s*$", line)
            if old:
                last_video.rotation = _normalize_rotation(float(old.group(1)))
    return info


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def _read_exif(path: str) -> Dict[str, str]:
    """Camera details from a photo, if Pillow is installed. Never raises."""
    try:
        from PIL import Image
        with Image.open(path) as image:
            exif = image.getexif()
            found: Dict[str, str] = {}
            if exif.get(271):
                found["camera_make"] = str(exif[271]).strip()
            if exif.get(272):
                found["camera_model"] = str(exif[272]).strip()
            taken = exif.get_ifd(0x8769).get(36867) or exif.get(306)
            if taken:
                found["date_taken"] = str(taken)
            return found
    except Exception:
        return {}


def probe(path: str, use_ffprobe: bool = True) -> MediaInfo:
    if not os.path.isfile(path):
        raise ProbeError("File not found")
    kind = classify(path)
    if kind is None:
        raise ProbeError("Unsupported file type")

    ffprobe = find_ffprobe() if use_ffprobe else None
    try:
        if ffprobe:
            result = run_tool([ffprobe, "-v", "error", "-print_format", "json",
                               "-show_format", "-show_streams", path])
            if result.returncode != 0:
                message = result.stderr.decode("utf-8", "replace").strip().splitlines()
                raise ProbeError(message[-1] if message else "Could not read the file")
            info = parse_ffprobe_json(json.loads(result.stdout.decode("utf-8", "replace")), path)
        else:
            ffmpeg = find_ffmpeg()
            if not ffmpeg:
                raise ProbeError("FFmpeg was not found. Install the requirements or set "
                                 "EASY_MOVIE_STUDIO_FFMPEG_DIR.")
            result = run_tool([ffmpeg, "-hide_banner", "-nostdin", "-i", path])
            info = parse_ffmpeg_info(result.stderr.decode("utf-8", "replace"), path)
    except (OSError, ValueError) as exc:  # subprocess failure or bad JSON
        raise ProbeError(f"Could not read the file: {exc}") from exc

    info.kind = kind
    stat = os.stat(path)
    info.size_bytes = stat.st_size
    info.modified = stat.st_mtime
    if kind == KIND_IMAGE:
        info.duration = None
        info.audio = None
        info.audio_streams = 0
        if info.video is None:
            raise ProbeError("Not a readable image")
        info.metadata.update(_read_exif(path))
    elif kind == KIND_VIDEO:
        if info.video is None or info.video.width <= 0:
            raise ProbeError("No video stream found")
    else:
        if info.audio is None:
            raise ProbeError("No audio stream found")
        info.video = None
        info.video_streams = 0
    if kind != KIND_IMAGE and not info.duration:
        raise ProbeError("Could not determine the duration")
    return info
