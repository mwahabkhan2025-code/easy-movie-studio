"""Small pure helpers."""

from __future__ import annotations


def format_time(seconds: float) -> str:
    """Format like Movie Maker's preview clock: 00:23.70 (hours only when needed)."""
    if seconds < 0:
        seconds = 0.0
    total_hundredths = int(round(seconds * 100))
    hundredths = total_hundredths % 100
    total_seconds = total_hundredths // 100
    secs = total_seconds % 60
    minutes = (total_seconds // 60) % 60
    hours = total_seconds // 3600
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}.{hundredths:02d}"
    return f"{minutes:02d}:{secs:02d}.{hundredths:02d}"
