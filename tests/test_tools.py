"""Tests for engine/tools.py's FFmpeg/ffprobe search order: EASY_MOVIE_STUDIO_FFMPEG_DIR, then
the packaged app's own folder (when frozen), then PATH, then imageio-ffmpeg's bundled
binary. Each layer is tested in isolation with mocks, since depending on the real
environment's actual ffmpeg install would make the test non-deterministic."""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from easy_movie_studio.engine import tools


class FindToolSearchOrderTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.env_patcher = mock.patch.dict(os.environ, {}, clear=False)
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)
        os.environ.pop("EASY_MOVIE_STUDIO_FFMPEG_DIR", None)

    def touch(self, *parts) -> str:
        path = os.path.join(self.dir, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"")
        return path

    def test_env_dir_is_checked_first(self):
        env_dir = os.path.join(self.dir, "envdir")
        os.makedirs(env_dir)
        expected = self.touch("envdir", "ffmpeg.exe")
        os.environ["EASY_MOVIE_STUDIO_FFMPEG_DIR"] = env_dir
        with mock.patch.object(tools, "_app_dir", return_value=None), \
             mock.patch("shutil.which", return_value="/usr/bin/should-not-be-used"):
            self.assertEqual(tools.find_tool("ffmpeg"), expected)

    def test_env_dir_without_exe_suffix_also_matches(self):
        env_dir = os.path.join(self.dir, "envdir")
        os.makedirs(env_dir)
        expected = self.touch("envdir", "ffmpeg")  # no .exe, as on Linux/Mac
        os.environ["EASY_MOVIE_STUDIO_FFMPEG_DIR"] = env_dir
        with mock.patch.object(tools, "_app_dir", return_value=None), \
             mock.patch("shutil.which", return_value=None):
            self.assertEqual(tools.find_tool("ffmpeg"), expected)

    def test_app_dir_is_checked_when_frozen_and_env_var_is_unset(self):
        app_dir = os.path.join(self.dir, "appdir")
        os.makedirs(app_dir)
        expected = self.touch("appdir", "ffmpeg.exe")
        with mock.patch.object(tools, "_app_dir", return_value=app_dir), \
             mock.patch("shutil.which", return_value=None):
            self.assertEqual(tools.find_tool("ffmpeg"), expected)

    def test_app_dir_is_not_consulted_when_not_frozen(self):
        # _app_dir() itself returns None unless sys.frozen is set -- confirm that
        # directly, independent of any mocking of the search order.
        with mock.patch.object(sys, "frozen", False, create=True):
            self.assertIsNone(tools._app_dir())

    def test_app_dir_resolves_from_sys_executable_when_frozen(self):
        fake_exe = os.path.join(self.dir, "EasyMovieStudio.exe")
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "executable", fake_exe):
            self.assertEqual(tools._app_dir(), self.dir)

    def test_env_dir_takes_priority_over_app_dir(self):
        env_dir = os.path.join(self.dir, "envdir")
        app_dir = os.path.join(self.dir, "appdir")
        os.makedirs(env_dir)
        os.makedirs(app_dir)
        expected = self.touch("envdir", "ffmpeg.exe")
        self.touch("appdir", "ffmpeg.exe")  # should be shadowed
        os.environ["EASY_MOVIE_STUDIO_FFMPEG_DIR"] = env_dir
        with mock.patch.object(tools, "_app_dir", return_value=app_dir), \
             mock.patch("shutil.which", return_value=None):
            self.assertEqual(tools.find_tool("ffmpeg"), expected)

    def test_falls_back_to_path_when_nothing_else_matches(self):
        with mock.patch.object(tools, "_app_dir", return_value=None), \
             mock.patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            self.assertEqual(tools.find_tool("ffmpeg"), "/usr/bin/ffmpeg")

    def test_ffprobe_has_no_bundled_fallback(self):
        # Only ffmpeg ships inside imageio-ffmpeg -- ffprobe genuinely has nowhere
        # left to come from once PATH and the app's own folder are exhausted.
        with mock.patch.object(tools, "_app_dir", return_value=None), \
             mock.patch("shutil.which", return_value=None):
            self.assertIsNone(tools.find_tool("ffprobe"))

    def test_ffmpeg_falls_back_to_the_bundled_binary(self):
        with mock.patch.object(tools, "_app_dir", return_value=None), \
             mock.patch("shutil.which", return_value=None), \
             mock.patch.object(tools, "_bundled_ffmpeg", return_value="/bundled/ffmpeg"):
            self.assertEqual(tools.find_tool("ffmpeg"), "/bundled/ffmpeg")


if __name__ == "__main__":
    unittest.main()
