import json
import os
import shutil
import tempfile
import unittest

from mmclone.model import (Clip, Project, ProjectFormatError, Transition, FORMAT_VERSION)


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def sample_project(self, media_dir):
        project = Project.new("Holiday")
        video = project.main_track
        video.add_clip(Clip.from_video(os.path.join(media_dir, "a.mp4"), 10.0))
        second = Clip.from_video(os.path.join(media_dir, "b.mp4"), 6.0,
                                 transition_in=Transition("fade", 1.0), effect="sepia")
        video.add_clip(second)
        video.add_clip(Clip.from_image(os.path.join(media_dir, "p.jpg")))
        project.tracks[1].add_clip(Clip.from_audio(os.path.join(media_dir, "m.mp3"), 60.0,
                                                   start=2.0))
        return project

    def test_new_project_defaults(self):
        project = Project.new()
        self.assertEqual([t.kind for t in project.tracks], ["video", "audio"])
        self.assertTrue(project.main_track.ripple)
        self.assertFalse(project.tracks[1].ripple)
        self.assertEqual(project.duration, 0.0)

    def test_duration_is_longest_track(self):
        project = self.sample_project(self.tmp)
        video_len = 10 + 6 - 1.0 + 7
        self.assertEqual(project.main_track.duration, video_len)
        self.assertEqual(project.duration, 62.0)  # music: 2 + 60

    def test_aspect_presets(self):
        project = Project.new()
        self.assertEqual(project.settings.aspect_label, "16:9")
        project.set_aspect("4:3")
        self.assertEqual((project.settings.width, project.settings.height), (1440, 1080))
        project.set_aspect("9:16")
        self.assertEqual(project.settings.aspect_label, "9:16")
        with self.assertRaises(ValueError):
            project.set_aspect("5:7")
        project.settings.width = 1000
        self.assertEqual(project.settings.aspect_label, "custom")

    def test_find_clip_and_tracks(self):
        project = self.sample_project(self.tmp)
        clip = project.tracks[1].clips[0]
        track, found = project.find_clip(clip.id)
        self.assertIs(track, project.tracks[1])
        self.assertIs(found, clip)
        with self.assertRaises(KeyError):
            project.find_clip("nope")

    def test_cannot_remove_last_video_track(self):
        project = Project.new()
        with self.assertRaises(ValueError):
            project.remove_track(project.main_track.id)
        extra = project.add_track("video", "Overlay")
        self.assertFalse(extra.ripple)
        project.remove_track(project.main_track.id)
        self.assertEqual(len(project.video_tracks()), 1)

    def test_save_load_round_trip(self):
        project = self.sample_project(os.path.join(self.tmp, "media"))
        path = os.path.join(self.tmp, "holiday.mmproj")
        project.save(path)
        loaded = Project.load(path)
        self.assertEqual(loaded.to_dict(), project.to_dict())
        self.assertEqual(loaded.duration, project.duration)

    def test_saved_file_uses_relative_paths(self):
        project = self.sample_project(os.path.join(self.tmp, "media"))
        path = os.path.join(self.tmp, "holiday.mmproj")
        project.save(path)
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data["tracks"][0]["clips"][0]["source"], "media/a.mp4")
        self.assertEqual(data["format_version"], FORMAT_VERSION)

    def test_project_folder_can_be_moved(self):
        first = os.path.join(self.tmp, "one")
        os.makedirs(first)
        self.sample_project(os.path.join(first, "media")).save(os.path.join(first, "m.mmproj"))
        second = os.path.join(self.tmp, "two")
        shutil.copytree(first, second)
        loaded = Project.load(os.path.join(second, "m.mmproj"))
        self.assertEqual(loaded.main_track.clips[0].source,
                         os.path.join(second, "media", "a.mp4"))

    def test_save_leaves_no_temp_file_and_overwrites(self):
        path = os.path.join(self.tmp, "p.mmproj")
        project = Project.new("First")
        project.save(path)
        project.name = "Second"
        project.save(path)
        self.assertEqual(sorted(os.listdir(self.tmp)), ["p.mmproj"])
        self.assertEqual(Project.load(path).name, "Second")

    def test_load_rejects_bad_files(self):
        def write(name, text):
            path = os.path.join(self.tmp, name)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
            return path

        with self.assertRaises(ProjectFormatError):
            Project.load(write("junk.mmproj", "not json"))
        with self.assertRaises(ProjectFormatError):
            Project.load(write("list.mmproj", "[1, 2]"))
        with self.assertRaises(ProjectFormatError):
            Project.load(write("nover.mmproj", "{}"))
        with self.assertRaises(ProjectFormatError) as ctx:
            Project.load(write("new.mmproj", json.dumps({"format_version": 99})))
        self.assertIn("newer version", str(ctx.exception))
        damaged = {"format_version": 1, "tracks": [{"kind": "video",
                                                     "clips": [{"kind": "video"}]}]}
        with self.assertRaises(ProjectFormatError):
            Project.load(write("damaged.mmproj", json.dumps(damaged)))

    def test_unicode_names_survive(self):
        path = os.path.join(self.tmp, "u.mmproj")
        project = Project.new("சுற்றுலா 🎬")
        project.save(path)
        self.assertEqual(Project.load(path).name, "சுற்றுலா 🎬")


if __name__ == "__main__":
    unittest.main()
