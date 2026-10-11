"""GUI tests for autosave wiring in MainWindow: the periodic tick, clearing on a clean
save/exit, and the startup recovery prompt. Storage itself is covered without Qt in
test_autosave.py; this file only checks the wiring."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QMessageBox
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class MainWindowAutosaveWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mmclone.ui.theme import stylesheet
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(stylesheet())

    def setUp(self):
        import shutil
        import tempfile
        from mmclone.autosave import AutosaveManager
        from mmclone.demo import demo_project
        from mmclone.recent import RecentProjects
        from mmclone.settings import SettingsStore
        from mmclone.ui.main_window import MainWindow
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.autosave = AutosaveManager(os.path.join(self.tmp, "autosave"))
        self.store = SettingsStore(os.path.join(self.tmp, "settings.json"))
        self.window = MainWindow(demo_project(), RecentProjects(os.path.join(self.tmp, "r.json")),
                                 verify_media=False, settings_store=self.store,
                                 autosave=self.autosave)
        self.addCleanup(self.window.deleteLater)

    def test_timer_is_running_after_construction(self):
        self.assertTrue(self.window._autosave_timer.isActive())

    def test_tick_with_no_unsaved_changes_does_not_write_anything(self):
        self.window._dirty = False
        self.window._autosave_tick()
        self.assertIsNone(self.autosave.pending())

    def test_tick_with_unsaved_changes_writes_an_autosave(self):
        self.window._mark_dirty()
        self.window._autosave_tick()
        info = self.autosave.pending()
        self.assertIsNotNone(info)
        self.assertEqual(info.original_path, self.window.project_path)

    def test_a_clean_save_clears_any_pending_autosave(self):
        self.window._mark_dirty()
        self.window._autosave_tick()
        self.assertIsNotNone(self.autosave.pending())
        path = os.path.join(self.tmp, "movie.mmproj")
        self.window._write(path)
        self.assertIsNone(self.autosave.pending())

    def test_installing_a_new_project_clears_any_pending_autosave(self):
        from mmclone.model import Project
        self.window._mark_dirty()
        self.window._autosave_tick()
        self.assertIsNotNone(self.autosave.pending())
        self.window._install_project(Project.new(), None)
        self.assertIsNone(self.autosave.pending())

    def test_recovery_check_with_nothing_pending_does_not_prompt(self):
        from unittest import mock
        with mock.patch("mmclone.ui.main_window.QMessageBox.question") as question:
            self.window._check_autosave_recovery()
        question.assert_not_called()

    def test_declining_recovery_clears_the_autosave_and_keeps_current_project(self):
        from unittest import mock
        from mmclone.model import Clip, Project
        other = Project.new("Crashed Movie")
        other.main_track.add_clip(Clip.from_video("c.mp4", 2.0))
        self.autosave.save(other, "/somewhere/crashed.mmproj")
        original_name = self.window.project.name
        with mock.patch("mmclone.ui.main_window.QMessageBox.question",
                        return_value=QMessageBox.StandardButton.No):
            self.window._check_autosave_recovery()
        self.assertEqual(self.window.project.name, original_name)
        self.assertIsNone(self.autosave.pending())

    def test_accepting_recovery_installs_the_recovered_project_as_dirty(self):
        from unittest import mock
        from mmclone.model import Clip, Project
        other = Project.new("Crashed Movie")
        other.main_track.add_clip(Clip.from_video("c.mp4", 2.0))
        self.autosave.save(other, "/somewhere/crashed.mmproj")
        with mock.patch("mmclone.ui.main_window.QMessageBox.question",
                        return_value=QMessageBox.StandardButton.Yes):
            self.window._check_autosave_recovery()
        self.assertEqual(self.window.project.name, "Crashed Movie")
        self.assertEqual(self.window.project_path, "/somewhere/crashed.mmproj")
        self.assertTrue(self.window._dirty)

    def test_a_damaged_autosave_file_is_reported_and_cleared(self):
        from unittest import mock
        os.makedirs(self.autosave.directory, exist_ok=True)
        with open(self.autosave.project_path, "w", encoding="utf-8") as handle:
            handle.write("{not valid json")
        import json
        import time
        with open(os.path.join(self.autosave.directory, "autosave.json"), "w",
                  encoding="utf-8") as handle:
            json.dump({"original_path": None, "original_name": "X", "saved_at": time.time()},
                      handle)
        with mock.patch("mmclone.ui.main_window.QMessageBox.question",
                        return_value=QMessageBox.StandardButton.Yes), \
             mock.patch("mmclone.ui.main_window.QMessageBox.critical") as critical:
            self.window._check_autosave_recovery()
        self.assertTrue(critical.called)
        self.assertIsNone(self.autosave.pending())

    def test_close_event_clears_pending_autosave(self):
        from unittest import mock
        self.window._mark_dirty()
        self.window._autosave_tick()
        self.assertIsNotNone(self.autosave.pending())
        with mock.patch.object(self.window, "_confirm_discard", return_value=True):
            self.window.close()
        self.assertIsNone(self.autosave.pending())


if __name__ == "__main__":
    unittest.main()
