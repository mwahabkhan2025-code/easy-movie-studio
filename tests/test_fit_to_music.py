import unittest

from mmclone.engine.fit_to_music import compute_fit_to_music
from mmclone.model import Clip, Project


def project_with(video_durations, music_duration=None):
    """Every clip (including the last) gets 3x spare source material beyond its shown
    duration, so "extend the last clip" tests have real headroom to work with."""
    project = Project.new()
    for i, d in enumerate(video_durations):
        clip = Clip.from_video(f"v{i}.mp4", d * 3)
        clip.trim(src_out=d)
        project.main_track.add_clip(clip)
    if music_duration is not None:
        project.tracks[1].add_clip(Clip.from_audio("m.mp3", music_duration))
    return project


class FitToMusicTests(unittest.TestCase):
    def test_no_video_clips_returns_none(self):
        project = Project.new()
        project.tracks[1].add_clip(Clip.from_audio("m.mp3", 30.0))
        self.assertIsNone(compute_fit_to_music(project))

    def test_no_music_returns_none(self):
        project = project_with([5.0, 5.0])
        self.assertIsNone(compute_fit_to_music(project))

    def test_already_matching_returns_none(self):
        project = project_with([5.0, 5.0], music_duration=10.0)
        self.assertIsNone(compute_fit_to_music(project))

    def test_extends_a_photo_exactly_when_music_is_longer(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_image("p.jpg", 5.0))
        project.tracks[1].add_clip(Clip.from_audio("m.mp3", 12.0))
        result = compute_fit_to_music(project)
        self.assertIsNotNone(result)
        self.assertTrue(result.matched_exactly)
        self.assertEqual(result.new_out, 12.0)

    def test_shrinks_a_photo_exactly_when_music_is_shorter(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_image("p.jpg", 10.0))
        project.tracks[1].add_clip(Clip.from_audio("m.mp3", 4.0))
        result = compute_fit_to_music(project)
        self.assertEqual(result.new_out, 4.0)
        self.assertTrue(result.matched_exactly)

    def test_video_clip_extension_capped_by_its_own_media_length(self):
        project = Project.new()
        clip = Clip.from_video("v.mp4", 6.0)  # only 6 s of real source available
        clip.trim(src_out=4.0)                # currently showing 4 s of it
        project.main_track.add_clip(clip)
        project.tracks[1].add_clip(Clip.from_audio("m.mp3", 20.0))  # wants 20 s total
        result = compute_fit_to_music(project)
        self.assertFalse(result.matched_exactly)  # can't reach 20 s, only 6 s exist
        self.assertEqual(result.new_out, 6.0)

    def test_video_clip_shrink_is_never_capped(self):
        project = Project.new()
        clip = Clip.from_video("v.mp4", 10.0)
        project.main_track.add_clip(clip)
        project.tracks[1].add_clip(Clip.from_audio("m.mp3", 3.0))
        result = compute_fit_to_music(project)
        self.assertTrue(result.matched_exactly)
        self.assertEqual(result.new_out, 3.0)

    def test_only_the_last_clip_changes(self):
        project = project_with([5.0, 5.0, 5.0], music_duration=20.0)
        ids_before = [c.id for c in project.main_track.clips]
        result = compute_fit_to_music(project)
        self.assertEqual(result.clip_id, ids_before[-1])

    def test_multiple_music_clips_use_the_track_s_full_span(self):
        project = project_with([5.0], music_duration=None)
        first = Clip.from_audio("m1.mp3", 4.0)
        second = Clip.from_audio("m2.mp3", 3.0, start=4.0)  # placed right after the first
        project.tracks[1].add_clip(first)
        project.tracks[1].add_clip(second)
        result = compute_fit_to_music(project)
        self.assertEqual(result.target_duration, 7.0)

    def test_speed_is_accounted_for_in_the_extension(self):
        project = Project.new()
        clip = Clip.from_video("v.mp4", 20.0, speed=2.0)  # 20s of source, played at 2x
        clip.trim(src_out=16.0)  # currently showing (16-0)/2 = 8s, not the full clip
        project.main_track.add_clip(clip)
        project.tracks[1].add_clip(Clip.from_audio("m.mp3", 15.0))
        result = compute_fit_to_music(project)
        # 15s of timeline duration at 2x speed needs 30s of source (capped at 20s available)
        self.assertIsNotNone(result)
        self.assertEqual(result.new_out, 20.0)
        self.assertFalse(result.matched_exactly)


if __name__ == "__main__":
    unittest.main()
