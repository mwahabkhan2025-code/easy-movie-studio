"""GUI tests for the Compress/Convert and Extract Audio dialogs (controls and command
wiring only -- the threaded run itself is covered end to end, without Qt, in
test_file_tools.py's real-FFmpeg integration tests)."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class CompressVideoDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from .media_fixtures import FFMPEG, MediaSet
        if not FFMPEG:
            raise unittest.SkipTest("FFmpeg not available")
        cls.media = MediaSet()

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()

    def make_dialog(self):
        from mmclone.ui.file_tools_dialog import CompressVideoDialog
        dialog = CompressVideoDialog()
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_run_button_disabled_until_a_file_is_chosen(self):
        dialog = self.make_dialog()
        self.assertFalse(dialog.run_button.isEnabled())

    def test_choosing_a_video_populates_info_and_enables_run(self):
        from unittest import mock
        dialog = self.make_dialog()
        with mock.patch("mmclone.ui.file_tools_dialog.QFileDialog.getOpenFileName",
                        return_value=(self.media.video_av, "")):
            dialog._choose_input()
        self.assertEqual(dialog.input_path, self.media.video_av)
        self.assertTrue(dialog.run_button.isEnabled())
        self.assertIn("320x240", dialog.info_label.text())

    def test_choosing_an_audio_only_file_is_rejected(self):
        from unittest import mock
        dialog = self.make_dialog()
        with mock.patch("mmclone.ui.file_tools_dialog.QFileDialog.getOpenFileName",
                        return_value=(self.media.tone, "")), \
             mock.patch("mmclone.ui.file_tools_dialog.QMessageBox.critical") as box:
            dialog._choose_input()
        self.assertTrue(box.called)
        self.assertFalse(dialog.run_button.isEnabled())

    def test_switching_preset_updates_quality_field(self):
        dialog = self.make_dialog()
        recommended_crf = dialog.quality_box.value()
        index = dialog.preset_box.findData("mobile")
        dialog.preset_box.setCurrentIndex(index)
        self.assertNotEqual(dialog.quality_box.value(), recommended_crf)


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class ExtractAudioDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from .media_fixtures import FFMPEG, MediaSet
        if not FFMPEG:
            raise unittest.SkipTest("FFmpeg not available")
        cls.media = MediaSet()

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()

    def make_dialog(self):
        from mmclone.ui.file_tools_dialog import ExtractAudioDialog
        dialog = ExtractAudioDialog()
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_choosing_a_video_with_audio_enables_run(self):
        from unittest import mock
        dialog = self.make_dialog()
        with mock.patch("mmclone.ui.file_tools_dialog.QFileDialog.getOpenFileName",
                        return_value=(self.media.video_av, "")):
            dialog._choose_input()
        self.assertTrue(dialog.run_button.isEnabled())

    def test_choosing_a_silent_video_is_rejected(self):
        from unittest import mock
        dialog = self.make_dialog()
        with mock.patch("mmclone.ui.file_tools_dialog.QFileDialog.getOpenFileName",
                        return_value=(self.media.video_silent, "")), \
             mock.patch("mmclone.ui.file_tools_dialog.QMessageBox.critical") as box:
            dialog._choose_input()
        self.assertTrue(box.called)
        self.assertFalse(dialog.run_button.isEnabled())

    def test_choosing_an_audio_file_enables_run(self):
        from unittest import mock
        dialog = self.make_dialog()
        with mock.patch("mmclone.ui.file_tools_dialog.QFileDialog.getOpenFileName",
                        return_value=(self.media.tone, "")):
            dialog._choose_input()
        self.assertTrue(dialog.run_button.isEnabled())


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class MainWindowFileToolsWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mmclone.ui.theme import stylesheet
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(stylesheet())

    def setUp(self):
        import shutil
        import tempfile
        from mmclone.demo import demo_project
        from mmclone.recent import RecentProjects
        from mmclone.ui.main_window import MainWindow
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.window = MainWindow(demo_project(), RecentProjects(os.path.join(self.tmp, "r.json")))
        self.addCleanup(self.window.deleteLater)

    def test_compress_command_opens_the_dialog(self):
        from unittest import mock
        with mock.patch("mmclone.ui.main_window.CompressVideoDialog") as dialog_cls:
            dialog_cls.return_value.exec.return_value = None
            self.window.on_command("file.compress_video")
        self.assertTrue(dialog_cls.return_value.exec.called)

    def test_extract_audio_command_opens_the_dialog(self):
        from unittest import mock
        with mock.patch("mmclone.ui.main_window.ExtractAudioDialog") as dialog_cls:
            dialog_cls.return_value.exec.return_value = None
            self.window.on_command("file.extract_audio")
        self.assertTrue(dialog_cls.return_value.exec.called)


if __name__ == "__main__":
    unittest.main()
