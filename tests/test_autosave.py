"""Tests for mmclone/autosave.py: crash-recovery autosave storage (no Qt needed -- the
periodic timer and recovery prompt are UI wiring, covered in test_autosave_ui.py)."""

import json
import os
import shutil
import tempfile
import unittest

from mmclone.autosave import AutosaveInfo, AutosaveManager
from mmclone.model import Clip, Project


class AutosaveManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.manager = AutosaveManager(os.path.join(self.tmp, "autosave"))

    def make_project(self):
        project = Project.new("My Movie")
        project.main_track.add_clip(Clip.from_video("clip.mp4", 3.0))
        return project

    def test_pending_is_none_when_nothing_was_ever_saved(self):
        self.assertIsNone(self.manager.pending())

    def test_save_then_pending_reports_the_original_path_and_name(self):
        self.manager.save(self.make_project(), "/movies/my-movie.mmproj")
        info = self.manager.pending()
        self.assertIsInstance(info, AutosaveInfo)
        self.assertEqual(info.original_path, "/movies/my-movie.mmproj")
        self.assertEqual(info.original_name, "My Movie")
        self.assertGreater(info.saved_at, 0)

    def test_save_with_no_original_path_yet_is_reported_as_none(self):
        self.manager.save(self.make_project(), None)
        info = self.manager.pending()
        self.assertIsNone(info.original_path)

    def test_recover_reloads_the_saved_project(self):
        project = self.make_project()
        self.manager.save(project, None)
        recovered = self.manager.recover()
        self.assertEqual(recovered.name, "My Movie")
        self.assertEqual(len(recovered.main_track.clips), 1)

    def test_clear_removes_both_files_and_pending_becomes_none(self):
        self.manager.save(self.make_project(), None)
        self.assertTrue(os.path.isfile(self.manager.project_path))
        self.manager.clear()
        self.assertFalse(os.path.isfile(self.manager.project_path))
        self.assertIsNone(self.manager.pending())

    def test_clear_with_nothing_saved_does_not_raise(self):
        self.manager.clear()  # must not raise

    def test_later_save_overwrites_the_earlier_one(self):
        self.manager.save(self.make_project(), "/a.mmproj")
        second = self.make_project()
        second.name = "Second Cut"
        self.manager.save(second, "/b.mmproj")
        info = self.manager.pending()
        self.assertEqual(info.original_path, "/b.mmproj")
        self.assertEqual(info.original_name, "Second Cut")

    def test_pending_with_missing_project_file_but_present_meta_is_none(self):
        self.manager.save(self.make_project(), None)
        os.remove(self.manager.project_path)
        self.assertIsNone(self.manager.pending())

    def test_pending_with_corrupted_meta_json_is_none(self):
        os.makedirs(self.manager.directory, exist_ok=True)
        with open(self.manager.project_path, "w", encoding="utf-8") as handle:
            handle.write("{}")
        with open(os.path.join(self.manager.directory, "autosave.json"), "w",
                  encoding="utf-8") as handle:
            handle.write("{not valid json")
        self.assertIsNone(self.manager.pending())

    def test_pending_with_a_json_list_instead_of_object_is_none(self):
        os.makedirs(self.manager.directory, exist_ok=True)
        with open(self.manager.project_path, "w", encoding="utf-8") as handle:
            handle.write("{}")
        with open(os.path.join(self.manager.directory, "autosave.json"), "w",
                  encoding="utf-8") as handle:
            json.dump([1, 2, 3], handle)
        self.assertIsNone(self.manager.pending())

    def test_save_never_raises_when_the_directory_cant_be_created(self):
        manager = AutosaveManager("/root/not_writable_xyz/autosave")
        manager.save(self.make_project(), None)  # must not raise


if __name__ == "__main__":
    unittest.main()
