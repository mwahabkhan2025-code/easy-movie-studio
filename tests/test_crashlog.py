"""Tests for the global exception hook (mmclone/crashlog.py). No Qt needed -- the
GUI dialog it triggers is covered by on_crash being a plain callback, tested here with
a stand-in."""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from mmclone import crashlog


class WriteCrashLogTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(mock.patch.stopall)

    def raise_and_capture(self):
        try:
            raise ValueError("something broke")
        except ValueError:
            return sys.exc_info()

    def test_writes_a_file_containing_the_traceback(self):
        mock.patch.object(crashlog, "log_dir", return_value=self.dir).start()
        exc_type, exc_value, tb = self.raise_and_capture()
        path = crashlog.write_crash_log(exc_type, exc_value, tb)
        self.assertTrue(os.path.isfile(path))
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
        self.assertIn("something broke", content)
        self.assertIn("ValueError", content)
        self.assertIn("raise_and_capture", content)  # the actual frame, not a placeholder

    def test_includes_app_name_and_version_header(self):
        mock.patch.object(crashlog, "log_dir", return_value=self.dir).start()
        exc_type, exc_value, tb = self.raise_and_capture()
        path = crashlog.write_crash_log(exc_type, exc_value, tb)
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
        from mmclone import APP_NAME, __version__
        self.assertIn(APP_NAME, content)
        self.assertIn(__version__, content)

    def test_falls_back_to_temp_dir_when_the_log_dir_cant_be_created(self):
        mock.patch.object(crashlog, "log_dir", return_value="/root/not_writable_xyz").start()
        exc_type, exc_value, tb = self.raise_and_capture()
        path = crashlog.write_crash_log(exc_type, exc_value, tb)  # must not raise
        self.assertTrue(os.path.isfile(path))
        self.addCleanup(os.remove, path)

    def test_each_call_gets_a_distinct_filename(self):
        mock.patch.object(crashlog, "log_dir", return_value=self.dir).start()
        exc_type, exc_value, tb = self.raise_and_capture()
        path1 = crashlog.write_crash_log(exc_type, exc_value, tb)
        import time
        time.sleep(1.01)  # the timestamp has 1-second resolution
        path2 = crashlog.write_crash_log(exc_type, exc_value, tb)
        self.assertNotEqual(path1, path2)


class InstallHookTests(unittest.TestCase):
    def setUp(self):
        self.original_hook = sys.excepthook
        self.addCleanup(setattr, sys, "excepthook", self.original_hook)
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def test_install_replaces_sys_excepthook(self):
        crashlog.install(on_crash=None)
        self.assertIsNot(sys.excepthook, self.original_hook)

    def test_on_crash_is_called_with_summary_and_log_path(self):
        with mock.patch.object(crashlog, "log_dir", return_value=self.dir):
            calls = []
            crashlog.install(on_crash=lambda summary, path: calls.append((summary, path)))
            try:
                raise RuntimeError("boom")
            except RuntimeError:
                sys.excepthook(*sys.exc_info())
            self.assertEqual(len(calls), 1)
            summary, path = calls[0]
            self.assertIn("RuntimeError", summary)
            self.assertIn("boom", summary)
            self.assertTrue(os.path.isfile(path))

    def test_a_broken_on_crash_handler_does_not_raise(self):
        with mock.patch.object(crashlog, "log_dir", return_value=self.dir):
            def bad_handler(summary, path):
                raise RuntimeError("the handler itself is broken")
            crashlog.install(on_crash=bad_handler)
            try:
                raise ValueError("original problem")
            except ValueError:
                sys.excepthook(*sys.exc_info())  # must not propagate bad_handler's exception

    def test_keyboard_interrupt_is_passed_through_not_logged(self):
        with mock.patch.object(crashlog, "log_dir", return_value=self.dir):
            calls = []
            crashlog.install(on_crash=lambda s, p: calls.append((s, p)))
            try:
                raise KeyboardInterrupt()
            except KeyboardInterrupt:
                sys.excepthook(*sys.exc_info())
            self.assertEqual(calls, [])
            self.assertEqual(os.listdir(self.dir), [])


if __name__ == "__main__":
    unittest.main()
