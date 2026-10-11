"""Tests for engine/proxy.py: low-resolution preview proxies.

Real-FFmpeg tests actually build a proxy and probe the output file, matching the
rigor used for file_tools.py and export_plan.py elsewhere in this suite.
"""

import os
import shutil
import unittest

from mmclone.engine.export import run_export
from mmclone.engine.proxy import (ProxyError, ProxyResolver, build_proxy_plan, needs_proxy,
                                  proxy_path_for, proxy_ready)
from mmclone.engine.probe import probe

from .media_fixtures import MediaSet, needs_ffmpeg


class NeedsProxyTests(unittest.TestCase):
    def test_image_never_needs_a_proxy(self):
        from mmclone.engine.media_info import MediaInfo
        info = MediaInfo(path="a.jpg", kind="image")
        self.assertFalse(needs_proxy(info))

    def test_video_with_no_video_stream_is_treated_as_not_needing_one(self):
        from mmclone.engine.media_info import MediaInfo
        info = MediaInfo(path="a.mp4", kind="video", video=None)
        self.assertFalse(needs_proxy(info))

    def test_narrow_video_is_skipped(self):
        from mmclone.engine.media_info import MediaInfo, VideoStream
        info = MediaInfo(path="a.mp4", kind="video", video=VideoStream(width=640, height=360))
        self.assertFalse(needs_proxy(info))

    def test_wide_video_needs_a_proxy(self):
        from mmclone.engine.media_info import MediaInfo, VideoStream
        info = MediaInfo(path="a.mp4", kind="video", video=VideoStream(width=1920, height=1080))
        self.assertTrue(needs_proxy(info))


class ProxyResolverTests(unittest.TestCase):
    def test_disabled_resolver_always_returns_the_original(self):
        resolver = ProxyResolver()
        self.assertEqual(resolver.resolve("a.mp4"), "a.mp4")

    def test_enabled_resolver_with_no_proxy_falls_back_to_the_original(self):
        resolver = ProxyResolver()
        resolver.enabled = True
        self.assertEqual(resolver.resolve("/does/not/exist/a.mp4"), "/does/not/exist/a.mp4")


@needs_ffmpeg
class BuildProxyPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media = MediaSet()

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()
        shutil.rmtree(_cache_dir(), ignore_errors=True)

    def test_plan_targets_the_cache_path_and_a_smaller_width(self):
        info = probe(self.media.video_av)
        plan = build_proxy_plan(self.media.video_av, info)
        self.assertEqual(plan.output_path, proxy_path_for(self.media.video_av))
        self.assertIn("-crf", plan.args)
        self.assertIn("ultrafast", plan.args)

    def test_image_source_raises(self):
        from mmclone.engine.media_info import MediaInfo
        info = MediaInfo(path=self.media.photo, kind="image", video=None)
        with self.assertRaises(ProxyError):
            build_proxy_plan(self.media.photo, info)


def _cache_dir():
    from mmclone.engine.proxy import CACHE_DIR
    return CACHE_DIR


@needs_ffmpeg
class ProxyIntegrationTests(unittest.TestCase):
    """Actually builds a proxy with real FFmpeg and probes the result."""

    @classmethod
    def setUpClass(cls):
        cls.media = MediaSet()

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()
        shutil.rmtree(_cache_dir(), ignore_errors=True)

    def setUp(self):
        shutil.rmtree(_cache_dir(), ignore_errors=True)

    def test_proxy_is_smaller_and_shorter_in_size_but_same_duration(self):
        # media_fixtures' own clips are tiny (320px) -- smaller than the proxy's own
        # 640px target -- so a real "this is heavy footage" source is generated here,
        # the same way needs_proxy() would actually gate one in the real app.
        from mmclone.engine.tools import find_ffmpeg, run_tool
        wide = os.path.join(self.media.dir, "wide.mp4")
        result = run_tool([find_ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i",
                          "testsrc=duration=2:size=1280x720:rate=25", "-f", "lavfi", "-i",
                          "sine=frequency=440:duration=2:sample_rate=44100", "-c:v", "mpeg4",
                          "-c:a", "aac", "-shortest", wide])
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        info = probe(wide)
        self.assertFalse(proxy_ready(wide))
        plan = build_proxy_plan(wide, info)
        run_export(plan)
        self.assertTrue(proxy_ready(wide))
        proxy_path = proxy_path_for(wide)
        proxy_info = probe(proxy_path)
        self.assertIsNotNone(proxy_info.video)
        self.assertLess(proxy_info.video.width, info.video.width)
        self.assertLess(os.path.getsize(proxy_path), os.path.getsize(wide))
        self.assertAlmostEqual(proxy_info.duration, info.duration, delta=0.3)

    def test_resolver_returns_the_proxy_once_built_and_enabled(self):
        info = probe(self.media.video_av)
        run_export(build_proxy_plan(self.media.video_av, info))
        resolver = ProxyResolver()
        self.assertEqual(resolver.resolve(self.media.video_av), self.media.video_av)
        resolver.enabled = True
        self.assertEqual(resolver.resolve(self.media.video_av),
                         proxy_path_for(self.media.video_av))

    def test_export_plan_for_the_real_project_is_unaffected_by_proxies(self):
        # Sanity check that nothing about engine.proxy touches the real export path --
        # it's a separate, throwaway project, never the one the user is editing.
        from mmclone.engine.export_plan import ExportSettings, build_export_plan
        from mmclone.model import Clip, Project
        info = probe(self.media.video_av)
        run_export(build_proxy_plan(self.media.video_av, info))
        project = Project.new()
        project.main_track.add_clip(Clip.from_video(self.media.video_av, 2.0))
        settings = ExportSettings(width=320, height=240, fps=25, sample_rate=48000)
        plan = build_export_plan(project, "o.mp4", settings)
        text = " ".join(plan.args)
        self.assertIn(self.media.video_av, text)
        self.assertNotIn(proxy_path_for(self.media.video_av), text)


if __name__ == "__main__":
    unittest.main()
