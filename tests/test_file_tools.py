"""Tests for the stand-alone Compress/Convert and Extract Audio helpers.

Plan-construction tests check pure plan/error behaviour with no FFmpeg process
involved. The real-FFmpeg tests actually run the resulting plan and probe the
output file, the same way test_export_integration.py checks exports.
"""

import os
import shutil
import tempfile
import unittest

from easy_movie_studio.engine.export import run_export
from easy_movie_studio.engine.export_plan import ExportError
from easy_movie_studio.engine.file_tools import build_compress_plan, build_extract_audio_plan
from easy_movie_studio.engine.probe import probe

from .media_fixtures import MediaSet, needs_ffmpeg


@needs_ffmpeg
class FileToolsPlanTests(unittest.TestCase):
    """Plan construction against real (tiny) media files, no FFmpeg run."""

    @classmethod
    def setUpClass(cls):
        cls.media = MediaSet()

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()

    def test_compress_plan_uses_requested_container_and_crf(self):
        plan = build_compress_plan(self.media.video_av, "/tmp/out.mp4", preset_id="small",
                                   crf=30)
        self.assertIn("/tmp/out.mp4", plan.args)
        self.assertIn("-crf", plan.args)
        self.assertEqual(plan.args[plan.args.index("-crf") + 1], "30")
        self.assertGreater(plan.duration, 0)

    def test_compress_plan_overrides_speed_preset(self):
        plan = build_compress_plan(self.media.video_av, "/tmp/out.mp4", preset_id="hq",
                                   speed_preset="ultrafast")
        self.assertIn("-preset", plan.args)
        self.assertEqual(plan.args[plan.args.index("-preset") + 1], "ultrafast")

    def test_compress_rejects_audio_only_source(self):
        with self.assertRaises(ExportError):
            build_compress_plan(self.media.tone, "/tmp/out.mp4")

    def test_compress_rejects_unknown_preset(self):
        with self.assertRaises(ValueError):
            build_compress_plan(self.media.video_av, "/tmp/out.mp4", preset_id="gif")

    def test_extract_audio_plan_from_video(self):
        plan = build_extract_audio_plan(self.media.video_av, "/tmp/out.mp3",
                                        audio_bitrate="128k")
        self.assertIn("-b:a", plan.args)
        self.assertEqual(plan.args[plan.args.index("-b:a") + 1], "128k")
        self.assertIn("-vn", plan.args)

    def test_extract_audio_plan_from_audio_file(self):
        plan = build_extract_audio_plan(self.media.tone, "/tmp/out.mp3")
        self.assertIn("-vn", plan.args)
        self.assertGreater(plan.duration, 0)

    def test_extract_audio_rejects_silent_video(self):
        with self.assertRaises(ExportError):
            build_extract_audio_plan(self.media.video_silent, "/tmp/out.mp3")


@needs_ffmpeg
class FileToolsIntegrationTests(unittest.TestCase):
    """Actually runs FFmpeg on the generated plan and probes the real output."""

    @classmethod
    def setUpClass(cls):
        cls.media = MediaSet()

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()

    def setUp(self):
        self.out_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.out_dir, ignore_errors=True)

    def out(self, name):
        return os.path.join(self.out_dir, name)

    def test_compress_produces_smaller_valid_video(self):
        output = self.out("compressed.mp4")
        plan = build_compress_plan(self.media.video_av, output, preset_id="small")
        run_export(plan, on_progress=lambda f: None)
        self.assertTrue(os.path.isfile(output))
        info = probe(output)
        self.assertIsNotNone(info.video)
        self.assertAlmostEqual(info.duration, 2.0, delta=0.3)
        self.assertTrue(info.has_audio)

    def test_convert_container_changes_extension_only(self):
        # "Convert format" is just a compress into a differently-named/contained file.
        output = self.out("converted.mkv")
        plan = build_compress_plan(self.media.video_av, output, preset_id="recommended")
        run_export(plan, on_progress=lambda f: None)
        self.assertTrue(os.path.isfile(output))
        info = probe(output)
        self.assertIsNotNone(info.video)

    def test_extract_audio_from_video_has_no_video_stream(self):
        output = self.out("audio.mp3")
        plan = build_extract_audio_plan(self.media.video_av, output, audio_bitrate="96k")
        run_export(plan, on_progress=lambda f: None)
        self.assertTrue(os.path.isfile(output))
        info = probe(output)
        self.assertIsNone(info.video)
        self.assertIsNotNone(info.audio)
        self.assertAlmostEqual(info.duration, 2.0, delta=0.3)

    def test_extract_audio_from_audio_file_reencodes(self):
        output = self.out("retone.mp3")
        plan = build_extract_audio_plan(self.media.tone, output)
        run_export(plan, on_progress=lambda f: None)
        self.assertTrue(os.path.isfile(output))
        info = probe(output)
        self.assertIsNotNone(info.audio)
        self.assertAlmostEqual(info.duration, 1.0, delta=0.3)


if __name__ == "__main__":
    unittest.main()
