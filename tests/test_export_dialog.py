"""GUI tests for the Save Movie dialog's controls (not the threaded export itself,
which is covered end to end in test_export_integration.py)."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class SaveMovieDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_dialog(self, preset="recommended"):
        from mmclone.model import Clip, Project
        from mmclone.ui.export_dialog import SaveMovieDialog
        project = Project.new("Demo")
        project.main_track.add_clip(Clip.from_video("a.mp4", 10.0))
        dialog = SaveMovieDialog(project, silent_sources=set(), default_preset=preset)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_defaults_come_from_the_recommended_preset(self):
        dialog = self.make_dialog("recommended")
        self.assertEqual(dialog.current_preset_id(), "recommended")
        self.assertTrue(dialog.quality_box.isEnabled())
        self.assertGreater(dialog.quality_box.value(), 0)
        self.assertIn("about", dialog.size_label.text())

    def test_audio_preset_disables_video_only_controls(self):
        dialog = self.make_dialog("audio")
        self.assertFalse(dialog.quality_box.isEnabled())
        self.assertFalse(dialog.speed_box.isEnabled())

    def test_changing_quality_updates_the_estimate(self):
        dialog = self.make_dialog("hq")
        low_crf_text = dialog.size_label.text()
        dialog.quality_box.setValue(40)  # much lower quality -> smaller estimate
        self.assertNotEqual(dialog.size_label.text(), low_crf_text)

    def test_switching_preset_updates_quality_field(self):
        dialog = self.make_dialog("recommended")
        recommended_crf = dialog.quality_box.value()
        index = dialog.preset_box.findData("mobile")
        dialog.preset_box.setCurrentIndex(index)
        self.assertNotEqual(dialog.quality_box.value(), recommended_crf)
        self.assertEqual(dialog.current_preset_id(), "mobile")

    def test_current_settings_reflect_the_ui(self):
        dialog = self.make_dialog("standard")
        dialog.quality_box.setValue(30)
        settings = dialog._current_settings()
        self.assertEqual(settings.crf, 30)
        self.assertEqual(settings.output_kind, "video")


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class MainWindowExportWiringTests(unittest.TestCase):
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

    def test_empty_project_refuses_to_open_the_dialog(self):
        from mmclone.model import Project
        self.window._install_project(Project.new(), None)
        self.window.open_save_movie_dialog()  # should just show a status message, not raise
        self.assertIn("Add a video", self.window.statusBar().currentMessage())

    def test_save_movie_command_opens_with_the_right_preset(self):
        from unittest import mock
        with mock.patch("mmclone.ui.main_window.SaveMovieDialog") as dialog_cls:
            dialog_cls.return_value.exec.return_value = None
            self.window.on_command("file.save_movie/hq")
        args, _kwargs = dialog_cls.call_args
        self.assertEqual(args[3], "hq")  # (project, silent_sources, default_dir, preset_id)

    def test_export_preset_gallery_also_opens_the_dialog(self):
        from unittest import mock
        with mock.patch("mmclone.ui.main_window.SaveMovieDialog") as dialog_cls:
            dialog_cls.return_value.exec.return_value = None
            self.window.on_command("home.export_preset/mobile")
        args, _kwargs = dialog_cls.call_args
        self.assertEqual(args[3], "mobile")

    def test_silent_sources_are_passed_from_probed_media(self):
        from unittest import mock
        from mmclone.engine.media_info import MediaInfo
        clip = self.window.storyboard.clips()[0]
        self.window.media[clip.source] = MediaInfo(path=clip.source, kind="video",
                                                    duration=5.0, audio=None)
        with mock.patch("mmclone.ui.main_window.SaveMovieDialog") as dialog_cls:
            dialog_cls.return_value.exec.return_value = None
            self.window.on_command("file.save_movie/recommended")
        args, _kwargs = dialog_cls.call_args
        self.assertIn(clip.source, args[1])


if __name__ == "__main__":
    unittest.main()
