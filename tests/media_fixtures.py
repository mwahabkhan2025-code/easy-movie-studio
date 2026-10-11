"""Generates tiny real media files with FFmpeg for tests. Skips when FFmpeg is missing."""

import os
import shutil
import tempfile
import unittest

from mmclone.engine.tools import find_ffmpeg, run_tool

FFMPEG = find_ffmpeg()
needs_ffmpeg = unittest.skipUnless(FFMPEG, "FFmpeg not available")


def _make(args, out):
    result = run_tool([FFMPEG, "-v", "error", "-y", *args, out], timeout=60)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace"))
    return out


class MediaSet:
    """Temp folder with: video_av.mp4 (320x240, 25 fps, 2 s, audio), video_silent.mp4
    (160x90, 30 fps, 1 s), photo.jpg (200x100), tone.wav (1 s)."""

    def __init__(self):
        self.dir = os.path.realpath(tempfile.mkdtemp(prefix="mmclone_test_"))
        d = self.dir
        self.video_av = _make(["-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=25",
                               "-f", "lavfi", "-i", "sine=frequency=440:duration=2:sample_rate=44100",
                               "-c:v", "mpeg4", "-c:a", "aac", "-shortest"],
                              os.path.join(d, "video_av.mp4"))
        self.video_silent = _make(["-f", "lavfi", "-i", "testsrc=duration=1:size=160x90:rate=30",
                                   "-c:v", "mpeg4"], os.path.join(d, "video_silent.mp4"))
        self.photo = _make(["-f", "lavfi", "-i", "testsrc=size=200x100", "-frames:v", "1"],
                           os.path.join(d, "photo.jpg"))
        self.tone = _make(["-f", "lavfi", "-i", "sine=frequency=300:duration=1"],
                          os.path.join(d, "tone.wav"))
        self.broken = os.path.join(d, "broken.mp4")
        with open(self.broken, "wb") as handle:
            handle.write(os.urandom(2048))

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)
