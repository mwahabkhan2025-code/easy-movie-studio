import unittest

from easy_movie_studio.engine.playback_plan import (build_segments, clamp_time, segment_index_at,
                                          signature, step_time, total_duration)
from easy_movie_studio.model import Clip, Track, Transition


def make_track(*durations, speeds=None):
    track = Track(kind="video")
    for i, d in enumerate(durations):
        track.add_clip(Clip.from_video(f"v{i}.mp4", d, speed=(speeds or {}).get(i, 1.0)))
    return track


class PlanTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(build_segments(Track(kind="video")), [])
        self.assertEqual(segment_index_at([], 1.0), -1)
        self.assertEqual(total_duration([]), 0.0)

    def test_sequential_segments(self):
        segs = build_segments(make_track(4, 6))
        self.assertEqual([(s.start, s.end) for s in segs], [(0, 4), (4, 10)])
        self.assertEqual(total_duration(segs), 10)

    def test_index_at_boundaries(self):
        segs = build_segments(make_track(4, 6))
        self.assertEqual(segment_index_at(segs, 0), 0)
        self.assertEqual(segment_index_at(segs, 3.999), 0)
        self.assertEqual(segment_index_at(segs, 4.0), 1)
        self.assertEqual(segment_index_at(segs, 10.0), 1)   # very end -> last
        self.assertEqual(segment_index_at(segs, 99), 1)
        self.assertEqual(segment_index_at(segs, -5), 0)

    def test_source_and_timeline_mapping_with_speed_and_trim(self):
        track = make_track(4, 10, speeds={1: 2.0})  # second clip lasts 5 s
        track.clips[1].trim(src_in=2.0, src_out=8.0)  # 6 s of source -> 3 s
        seg = build_segments(track)[1]
        self.assertEqual((seg.start, seg.end), (4, 7))
        self.assertEqual(seg.source_time(4), 2.0)
        self.assertEqual(seg.source_time(5), 4.0)
        self.assertEqual(seg.src_end, 8.0)
        self.assertEqual(seg.timeline_time(6.0), 6.0)

    def test_transition_cuts_the_earlier_clip(self):
        track = make_track(4, 6)
        track.clips[1].transition_in = Transition("fade", 1.0)
        first, second = build_segments(track)
        # the 1 s transition makes the second clip start at 3.0, overlapping the first
        self.assertEqual((first.start, first.end), (0, 3.0))
        self.assertEqual((second.start, second.end), (3.0, 9.0))
        self.assertEqual(first.src_end, 3.0)
        self.assertEqual(segment_index_at([first, second], 3.1), 1)

    def test_clamp_and_step(self):
        segs = build_segments(make_track(2))
        self.assertEqual(clamp_time(segs, 5), 2)
        self.assertEqual(clamp_time(segs, -1), 0)
        self.assertAlmostEqual(step_time(1.0, 25, 1), 1.04)
        self.assertAlmostEqual(step_time(1.0, 25, -1), 0.96)
        self.assertAlmostEqual(step_time(1.0, 0, 1), 1 + 1 / 30)

    def test_signature_changes_only_when_playback_changes(self):
        track = make_track(4, 6)
        before = signature(build_segments(track))
        self.assertEqual(before, signature(build_segments(track)))
        track.clips[0].rotate(90)
        self.assertNotEqual(before, signature(build_segments(track)))
        track.clips[0].rotate(-90)
        self.assertEqual(before, signature(build_segments(track)))
        track.clips[1].update(effect="sepia")  # not part of playback yet
        self.assertEqual(before, signature(build_segments(track)))


if __name__ == "__main__":
    unittest.main()
