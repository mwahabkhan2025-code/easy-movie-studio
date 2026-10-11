"""GUI tests for the Options dialog and its wiring into MainWindow: that File menu >
Options opens it pre-filled with the current settings, that accepting it persists and
applies the change, and that cancelling leaves everything untouched."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QDialog
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class OptionsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_dialog(self, settings=None):
        from mmclone.settings import AppSettings
        from mmclone.ui.options_dialog import OptionsDialog
        dialog = OptionsDialog(settings or AppSettings())
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_fields_start_at_the_given_settings(self):
        from mmclone.settings import AppSettings
        settings = AppSettings(default_export_preset="mobile", default_project_dir="/movies",
                               ffmpeg_dir="/opt/ffmpeg", proxy_min_width=1280)
        dialog = self.make_dialog(settings)
        self.assertEqual(dialog.preset_box.currentData(), "mobile")
        self.assertEqual(dialog.project_dir_row.text(), "/movies")
        self.assertEqual(dialog.ffmpeg_dir_row.text(), "/opt/ffmpeg")
        self.assertEqual(dialog.proxy_width_box.value(), 1280)

    def test_values_reflects_edited_fields(self):
        dialog = self.make_dialog()
        dialog.proxy_width_box.setValue(1600)
        dialog.ffmpeg_dir_row.edit.setText("/usr/local/ffmpeg")
        result = dialog.values()
        self.assertEqual(result.proxy_min_width, 1600)
        self.assertEqual(result.ffmpeg_dir, "/usr/local/ffmpeg")

    def test_browse_button_fills_in_the_chosen_folder(self):
        from unittest import mock
        dialog = self.make_dialog()
        with mock.patch("mmclone.ui.options_dialog.QFileDialog.getExistingDirectory",
                        return_value="/chosen/folder"):
            dialog.project_dir_row._browse()
        self.assertEqual(dialog.project_dir_row.text(), "/chosen/folder")


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class MainWindowOptionsWiringTests(unittest.TestCase):
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
        from mmclone.settings import SettingsStore
        from mmclone.ui.main_window import MainWindow
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(os.environ.pop, "MMCLONE_FFMPEG_DIR", None)
        self.store = SettingsStore(os.path.join(self.tmp, "settings.json"))
        self.window = MainWindow(demo_project(), RecentProjects(os.path.join(self.tmp, "r.json")),
                                 verify_media=False, settings_store=self.store)
        self.addCleanup(self.window.deleteLater)

    def test_window_loads_default_settings_on_start(self):
        from mmclone.settings import AppSettings
        self.assertEqual(self.window.settings, AppSettings())

    def test_file_options_command_is_routed_to_the_handler(self):
        self.assertIn("file.options", self.window._handlers)
        self.assertEqual(self.window._handlers["file.options"], self.window.open_options_dialog)

    def test_accepting_the_dialog_saves_and_applies_settings(self):
        from unittest import mock
        from mmclone.ui.options_dialog import OptionsDialog

        def fake_dialog(settings, parent=None):
            dialog = mock.Mock()
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.values.return_value = settings.__class__(
                default_export_preset="hq", default_project_dir="/movies",
                ffmpeg_dir="/opt/ffmpeg", proxy_min_width=1600)
            return dialog

        with mock.patch("mmclone.ui.main_window.OptionsDialog", side_effect=fake_dialog):
            self.window.open_options_dialog()

        self.assertEqual(self.window.settings.default_export_preset, "hq")
        self.assertEqual(self.window.settings.proxy_min_width, 1600)
        self.assertEqual(os.environ.get("MMCLONE_FFMPEG_DIR"), "/opt/ffmpeg")
        reloaded = self.store.load()
        self.assertEqual(reloaded.default_export_preset, "hq")

    def test_cancelling_the_dialog_leaves_settings_unchanged(self):
        from unittest import mock
        original = self.window.settings

        def fake_dialog(settings, parent=None):
            dialog = mock.Mock()
            dialog.exec.return_value = QDialog.DialogCode.Rejected
            return dialog

        with mock.patch("mmclone.ui.main_window.OptionsDialog", side_effect=fake_dialog):
            self.window.open_options_dialog()

        self.assertEqual(self.window.settings, original)
        self.assertFalse(os.path.isfile(self.store.store_path))

    def test_save_movie_falls_back_to_the_default_preset_from_settings(self):
        from unittest import mock
        self.window.settings.update(default_export_preset="youtube")
        with mock.patch("mmclone.ui.main_window.SaveMovieDialog") as dialog_cls:
            dialog_cls.return_value.exec.return_value = None
            self.window.open_save_movie_dialog()
        args, _ = dialog_cls.call_args
        self.assertEqual(args[3], "youtube")


if __name__ == "__main__":
    unittest.main()
