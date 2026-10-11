"""Plain data describing a media file (what ``probe`` returns)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass
class VideoStream:
    codec: str = ""
    profile: Optional[str] = None
    width: int = 0
    height: int = 0
    fps: Optional[float] = None
    bitrate: Optional[int] = None  # bits per second
    pix_fmt: Optional[str] = None
    rotation: int = 0  # degrees clockwise needed to display upright (0/90/180/270)

    @property
    def display_size(self) -> Tuple[int, int]:
        """Width and height as displayed, after applying the rotation flag."""
        if self.rotation in (90, 270):
            return self.height, self.width
        return self.width, self.height


@dataclass
class AudioStream:
    codec: str = ""
    profile: Optional[str] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    channel_layout: Optional[str] = None
    bitrate: Optional[int] = None


@dataclass
class MediaInfo:
    path: str
    kind: str  # "video", "image" or "audio"
    duration: Optional[float] = None  # seconds; None for images
    size_bytes: int = 0
    modified: Optional[float] = None  # POSIX timestamp
    container: str = ""
    bitrate: Optional[int] = None
    video: Optional[VideoStream] = None
    audio: Optional[AudioStream] = None
    video_streams: int = 0
    audio_streams: int = 0
    subtitle_streams: int = 0
    metadata: Dict[str, str] = field(default_factory=dict)

    @property
    def has_audio(self) -> bool:
        return self.audio is not None
