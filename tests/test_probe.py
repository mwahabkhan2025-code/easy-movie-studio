import json
import unittest

from easy_movie_studio.engine.probe import (ProbeError, classify, parse_ffmpeg_info, parse_ffprobe_json,
                                  probe)
from easy_movie_studio.engine.tools import find_ffprobe

from .media_fixtures import MediaSet, needs_ffmpeg

# Phone-style clip: H.264 with a display-matrix rotation and a "-90" flag, 4K portrait.
PHONE_FFMPEG_TEXT = """\
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'phone.mp4':
  Metadata:
    major_brand     : mp42
    creation_time   : 2024-05-01T10:20:30.000000Z
    com.apple.quicktime.model: iPhone 13
  Duration: 00:00:12.48, start: 0.000000, bitrate: 17213 kb/s
  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(tv, bt709, progressive), 3840x2160, 17007 kb/s, 29.97 fps, 29.97 tbr, 600 tbn (default)
    Metadata:
      handler_name    : Core Media Video
    Side data:
      displaymatrix: rotation of -90.00 degrees
  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706D), 48000 Hz, stereo, fltp, 191 kb/s (default)
At least one output file must be specified
"""

MP3_WITH_ART_TEXT = """\
Input #0, mp3, from 'song.mp3':
  Duration: 00:03:00.00, start: 0.025057, bitrate: 320 kb/s
  Stream #0:0: Audio: mp3, 44100 Hz, stereo, fltp, 320 kb/s
  Stream #0:1: Video: mjpeg (Baseline), yuvj444p(pc, bt470bg/unknown/unknown), 500x500 [SAR 1:1 DAR 1:1], 90k tbr, 90k tbn (attached pic)
At least one output file must be specified
"""


class ParserTests(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(classify("a.MP4"), "video")
        self.assertEqual(classify("a.JPG"), "image")
        self.assertEqual(classify("a.mp3"), "audio")
        self.assertIsNone(classify("a.txt"))

    def test_ffmpeg_text_phone_clip(self):
        info = parse_ffmpeg_info(PHONE_FFMPEG_TEXT, "phone.mp4")
        v, a = info.video, info.audio
        self.assertEqual((v.codec, v.profile, v.width, v.height), ("h264", "High", 3840, 2160))
        self.assertAlmostEqual(v.fps, 29.97)
        self.assertEqual(v.rotation, 90)
        self.assertEqual(v.display_size, (2160, 3840))
        self.assertEqual(v.pix_fmt, "yuv420p")
        self.assertEqual(v.bitrate, 17007000)
        self.assertEqual((a.codec, a.profile, a.sample_rate, a.channels), ("aac", "LC", 48000, 2))
        self.assertAlmostEqual(info.duration, 12.48)
        self.assertEqual(info.metadata["creation_time"], "2024-05-01T10:20:30.000000Z")
        self.assertNotIn("handler_name", info.metadata)

    def test_ffmpeg_text_ignores_album_art(self):
        info = parse_ffmpeg_info(MP3_WITH_ART_TEXT, "song.mp3")
        self.assertIsNone(info.video)
        self.assertEqual(info.video_streams, 0)
        self.assertEqual(info.audio.channels, 2)

    def test_ffmpeg_text_errors(self):
        with self.assertRaises(ProbeError) as ctx:
            parse_ffmpeg_info("x.mp4: Invalid data found when processing input", "x.mp4")
        self.assertIn("Invalid data", str(ctx.exception))
        with self.assertRaises(ProbeError):
            parse_ffmpeg_info("", "x.mp4")

    def test_ffprobe_json_rotation_and_audio(self):
        data = {"format": {"format_name": "mov,mp4", "duration": "5.5", "bit_rate": "1000000",
                           "tags": {"Title": "Hello"}},
                "streams": [
                    {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
                     "avg_frame_rate": "30000/1001", "pix_fmt": "yuv420p",
                     "side_data_list": [{"side_data_type": "Display Matrix", "rotation": -90}]},
                    {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000",
                     "channels": 2, "channel_layout": "stereo", "bit_rate": "128000"},
                    {"codec_type": "video", "codec_name": "mjpeg", "width": 10, "height": 10,
                     "disposition": {"attached_pic": 1}},
                ]}
        info = parse_ffprobe_json(data, "x.mp4")
        self.assertEqual(info.video.rotation, 90)
        self.assertAlmostEqual(info.video.fps, 29.97, places=2)
        self.assertEqual(info.video_streams, 1)
        self.assertEqual(info.metadata["title"], "Hello")
        self.assertEqual(info.audio.sample_rate, 48000)
        self.assertEqual(info.duration, 5.5)


@needs_ffmpeg
class RealFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media = MediaSet()

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()

    def check_video_av(self, info):
        self.assertEqual(info.kind, "video")
        self.assertEqual((info.video.width, info.video.height), (320, 240))
        self.assertAlmostEqual(info.video.fps, 25.0, places=1)
        self.assertAlmostEqual(info.duration, 2.0, delta=0.1)
        self.assertEqual(info.audio.sample_rate, 44100)
        self.assertEqual(info.audio.channels, 1)
        self.assertEqual(info.video.codec, "mpeg4")
        self.assertGreater(info.size_bytes, 1000)

    def test_probe_video_with_fallback_parser(self):
        self.check_video_av(probe(self.media.video_av, use_ffprobe=False))

    @unittest.skipUnless(find_ffprobe(), "ffprobe not available")
    def test_probe_video_with_ffprobe(self):
        self.check_video_av(probe(self.media.video_av, use_ffprobe=True))

    def test_both_methods_agree(self):
        if not find_ffprobe():
            self.skipTest("ffprobe not available")
        a = probe(self.media.video_silent, use_ffprobe=True)
        b = probe(self.media.video_silent, use_ffprobe=False)
        self.assertEqual((a.video.width, a.video.height), (b.video.width, b.video.height))
        self.assertAlmostEqual(a.video.fps, b.video.fps, places=1)
        self.assertAlmostEqual(a.duration, b.duration, delta=0.05)
        self.assertEqual(a.has_audio, b.has_audio)

    def test_video_without_audio(self):
        info = probe(self.media.video_silent, use_ffprobe=False)
        self.assertFalse(info.has_audio)
        self.assertEqual((info.video.width, info.video.height), (160, 90))

    def test_photo(self):
        info = probe(self.media.photo, use_ffprobe=False)
        self.assertEqual(info.kind, "image")
        self.assertIsNone(info.duration)
        self.assertEqual((info.video.width, info.video.height), (200, 100))

    def test_audio_file(self):
        info = probe(self.media.tone, use_ffprobe=False)
        self.assertEqual(info.kind, "audio")
        self.assertIsNone(info.video)
        self.assertAlmostEqual(info.duration, 1.0, delta=0.05)

    def test_errors(self):
        for path, fragment in ((self.media.broken, ""), (self.media.dir + "/nope.mp4", "not found"),
                               (self.media.dir + "/notes.txt", "Unsupported")):
            if path.endswith("notes.txt"):
                open(path, "w").close()
            with self.assertRaises(ProbeError) as ctx:
                probe(path, use_ffprobe=False)
            self.assertIn(fragment.lower(), str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
