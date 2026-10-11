import os
import unittest

from easy_movie_studio.engine.importer import (expand_paths, import_media, insert_position, nearest_aspect,
                                     nearest_fps, scan_media, suggest_settings)
from easy_movie_studio.engine.probe import probe
from easy_movie_studio.model import Clip, Track

from .media_fixtures import MediaSet, needs_ffmpeg


class PureHelperTests(unittest.TestCase):
    def test_nearest_aspect(self):
        self.assertEqual(nearest_aspect(1920, 1080), "16:9")
        self.assertEqual(nearest_aspect(1280, 720), "16:9")
        self.assertEqual(nearest_aspect(640, 480), "4:3")
        self.assertEqual(nearest_aspect(1080, 1920), "9:16")
        self.assertEqual(nearest_aspect(1000, 1000), "1:1")
        self.assertEqual(nearest_aspect(0, 0), "16:9")

    def test_nearest_fps(self):
        self.assertEqual(nearest_fps(29.97), 30.0)
        self.assertEqual(nearest_fps(23.976), 24.0)
        self.assertEqual(nearest_fps(59.94), 60.0)
        self.assertEqual(nearest_fps(15.0), 30.0)  # nothing close: keep default
        self.assertEqual(nearest_fps(None), 30.0)

    def test_insert_position(self):
        track = Track(kind="video")
        clips = [Clip.from_video("v.mp4", 5) for _ in range(3)]
        for c in clips:
            track.add_clip(c)
        self.assertEqual(insert_position(track, []), 3)
        self.assertEqual(insert_position(track, [clips[0].id]), 1)
        self.assertEqual(insert_position(track, [clips[0].id, clips[1].id]), 2)
        self.assertEqual(insert_position(track, ["unknown"]), 3)


class ExpandPathsTests(unittest.TestCase):
    def test_folder_expands_to_media_files_only(self):
        import os, shutil, tempfile
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        for name in ("b.mp4", "a.JPG", "notes.txt", "c.mp3"):
            open(os.path.join(tmp, name), "w").close()
        os.mkdir(os.path.join(tmp, "sub"))
        single = os.path.join(tmp, "notes.txt")
        result = expand_paths([tmp, single, ""])
        self.assertEqual([os.path.basename(p) for p in result], ["a.JPG", "b.mp4", "notes.txt"])


@needs_ffmpeg
class ImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media = MediaSet()

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()

    def test_import_builds_clips_and_reports_problems(self):
        result = import_media([self.media.video_av, self.media.photo, self.media.tone,
                               self.media.broken, self.media.dir + "/missing.mp4"])
        self.assertEqual([c.kind for c in result.clips], ["video", "image"])
        self.assertAlmostEqual(result.clips[0].duration, 2.0, delta=0.1)
        self.assertEqual(result.clips[1].duration, 7.0)
        self.assertEqual(set(result.infos), {self.media.video_av, self.media.photo})
        reasons = {os.path.basename(p): r for p, r in result.errors}
        self.assertIn("Add music", reasons["tone.wav"])
        self.assertIn("broken.mp4", reasons)
        self.assertIn("not found", reasons["missing.mp4"].lower())

    def test_audio_allowed_when_requested(self):
        result = import_media([self.media.tone], allowed_kinds=("audio",))
        self.assertEqual([c.kind for c in result.clips], ["audio"])

    def test_suggest_settings(self):
        info = probe(self.media.video_av)
        self.assertEqual(suggest_settings(info), ("4:3", 25.0))
        self.assertEqual(suggest_settings(probe(self.media.photo)), ("16:9", None))

    def test_scan_media_separates_problems(self):
        infos, problems = scan_media([self.media.video_av, self.media.video_av,
                                      self.media.dir + "/gone.mp4"])
        self.assertEqual(list(infos), [self.media.video_av])
        self.assertEqual(list(problems), [self.media.dir + "/gone.mp4"])


if __name__ == "__main__":
    unittest.main()
