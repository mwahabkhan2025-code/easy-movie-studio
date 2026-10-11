"""GUI tests for the proxy toggle: the status bar button, and that PlaybackController
actually asks its resolver before opening a video. Real proxy generation (FFmpeg) is
covered without Qt in test_proxy.py; this file only checks the wiring."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class PlaybackProxyResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_resolver_is_consulted_for_a_video_clip(self):
        from easy_movie_studio.model import Clip, Project
        from easy_movie_studio.ui.playback import PlaybackController
        calls = []

        def resolver(source):
            calls.append(source)
            return source

        player = PlaybackController()
        self.addCleanup(player.deleteLater)
        player.set_proxy_resolver(resolver)
        project = Project.new()
        project.main_track.add_clip(Clip.from_video("missing.mp4", 2.0))
        player.set_project(project)
        self.assertIn("missing.mp4", calls)

    def test_resolver_exception_falls_back_to_the_original_source(self):
        from easy_movie_studio.model import Clip, Project
        from easy_movie_studio.ui.playback import PlaybackController

        def bad_resolver(source):
            raise RuntimeError("boom")

        player = PlaybackController()
        self.addCleanup(player.deleteLater)
        player.set_proxy_resolver(bad_resolver)
        messages = []
        player.failed.connect(messages.append)
        project = Project.new()
        project.main_track.add_clip(Clip.from_video("missing.mp4", 2.0))
        player.set_project(project)
        player.play()  # forces the non-quiet "file not found" path
        self.assertTrue(messages)
        self.assertIn("missing.mp4", messages[0])  # the real source, not a mangled proxy path

    def test_no_resolver_set_plays_the_original(self):
        from easy_movie_studio.model import Clip, Project
        from easy_movie_studio.ui.playback import PlaybackController
        player = PlaybackController()
        self.addCleanup(player.deleteLater)
        project = Project.new()
        project.main_track.add_clip(Clip.from_video("missing.mp4", 2.0))
        player.set_project(project)  # no crash with the default (no-op) resolver


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class MainWindowProxyWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from easy_movie_studio.ui.theme import stylesheet
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(stylesheet())

    def setUp(self):
        import shutil
        import tempfile
        from easy_movie_studio.demo import demo_project
        from easy_movie_studio.recent import RecentProjects
        from easy_movie_studio.ui.main_window import MainWindow
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.window = MainWindow(demo_project(), RecentProjects(os.path.join(self.tmp, "r.json")),
                                 verify_media=False)
        self.addCleanup(self.window.deleteLater)

    def test_proxy_button_starts_unchecked_and_disabled_resolver(self):
        self.assertFalse(self.window.proxy_btn.isChecked())
        self.assertFalse(self.window.proxy_resolver.enabled)

    def test_checking_the_button_enables_the_resolver(self):
        self.window.proxy_btn.setChecked(True)
        self.assertTrue(self.window.proxy_resolver.enabled)

    def test_unchecking_disables_the_resolver_and_shows_a_message(self):
        self.window.proxy_btn.setChecked(True)
        self.window.proxy_btn.setChecked(False)
        self.assertFalse(self.window.proxy_resolver.enabled)
        self.assertIn("original", self.window.statusBar().currentMessage())

    def test_enabling_with_no_heavy_media_shows_a_ready_message_without_a_background_job(self):
        from unittest import mock
        with mock.patch.object(self.window.tasks, "submit") as submit:
            self.window.proxy_btn.setChecked(True)
        submit.assert_not_called()
        self.assertIn("proxies", self.window.statusBar().currentMessage().lower())

    def test_enabling_with_heavy_media_kicks_off_a_background_build(self):
        from unittest import mock
        from easy_movie_studio.engine.media_info import MediaInfo, VideoStream
        self.window.media["heavy.mp4"] = MediaInfo(path="heavy.mp4", kind="video", duration=5.0,
                                                    video=VideoStream(width=1920, height=1080))
        with mock.patch.object(self.window.tasks, "submit") as submit:
            self.window.proxy_btn.setChecked(True)
        self.assertTrue(submit.called)
        args, kwargs = submit.call_args
        pending = args[1]
        self.assertEqual([p for p, _ in pending], ["heavy.mp4"])


if __name__ == "__main__":
    unittest.main()
