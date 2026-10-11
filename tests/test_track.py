import unittest

from mmclone.model import Clip, Track, Transition


def video(duration, **kw):
    return Clip.from_video("v.mp4", duration, **kw)


class TrackTests(unittest.TestCase):
    def make_track(self, *durations):
        track = Track(kind="video")
        for d in durations:
            track.add_clip(video(d))
        return track

    def test_ripple_layout_is_sequential(self):
        track = self.make_track(4, 6, 2)
        spans = [(p.start, p.end) for p in track.layout()]
        self.assertEqual(spans, [(0, 4), (4, 10), (10, 12)])
        self.assertEqual(track.duration, 12)

    def test_transition_overlaps_and_shortens_total(self):
        track = self.make_track(4, 6)
        track.clips[1].transition_in = Transition("fade", 1.5)
        placed = track.layout()
        self.assertEqual((placed[1].start, placed[1].overlap), (2.5, 1.5))
        self.assertEqual(track.duration, 8.5)

    def test_transition_is_capped_at_half_of_neighbours(self):
        track = self.make_track(4, 6)
        track.clips[1].transition_in = Transition("fade", 10)
        self.assertEqual(track.layout()[1].overlap, 2.0)

    def test_transition_on_first_clip_is_ignored(self):
        track = self.make_track(4, 6)
        track.clips[0].transition_in = Transition("fade", 1)
        self.assertEqual(track.layout()[0].start, 0)

    def test_move_clip_reorders(self):
        track = self.make_track(1, 2, 3)
        ids = [c.id for c in track.clips]
        track.move_clip(ids[2], 0)
        self.assertEqual([c.id for c in track.clips], [ids[2], ids[0], ids[1]])
        self.assertEqual([p.start for p in track.layout()], [0, 3, 4])
        with self.assertRaises(IndexError):
            track.move_clip(ids[0], 5)

    def test_split_maps_timeline_time_to_source(self):
        track = Track(kind="video")
        clip = video(10.0)
        track.add_clip(clip)
        second = track.split_clip(clip.id, 4.0)
        self.assertEqual((clip.src_in, clip.src_out), (0.0, 4.0))
        self.assertEqual((second.src_in, second.src_out), (4.0, 10.0))
        self.assertEqual(track.clips, [clip, second])
        self.assertEqual(track.duration, 10.0)

    def test_split_respects_speed(self):
        track = Track(kind="video")
        clip = video(10.0, speed=2.0)  # lasts 5 s on the timeline
        track.add_clip(clip)
        second = track.split_clip(clip.id, 1.0)  # 1 s timeline = 2 s of source
        self.assertEqual(clip.src_out, 2.0)
        self.assertEqual(second.src_in, 2.0)
        self.assertAlmostEqual(clip.duration + second.duration, 5.0)

    def test_split_on_later_clip_and_transition_moves_correctly(self):
        track = self.make_track(4, 6)
        track.clips[1].transition_in = Transition("fade", 1.0)
        second_clip = track.clips[1]
        new = track.split_clip(second_clip.id, 5.0)  # clip starts at 3.0
        self.assertEqual(second_clip.src_out, 2.0)
        self.assertIsNone(new.transition_in)
        self.assertIsNotNone(second_clip.transition_in)

    def test_split_at_edges_or_outside_is_rejected(self):
        track = Track(kind="video")
        clip = video(5.0)
        track.add_clip(clip)
        for at in (0.0, 5.0, -1.0, 7.0):
            with self.assertRaises(ValueError):
                track.split_clip(clip.id, at)
        self.assertEqual(len(track.clips), 1)

    def test_split_image(self):
        track = Track(kind="video")
        photo = Clip.from_image("p.jpg", 6.0)
        track.add_clip(photo)
        second = track.split_clip(photo.id, 2.0)
        self.assertEqual((photo.duration, second.duration), (2.0, 4.0))

    def test_track_only_accepts_matching_kinds(self):
        with self.assertRaises(ValueError):
            Track(kind="audio").add_clip(video(3))
        with self.assertRaises(ValueError):
            Track(kind="video").add_clip(Clip.from_audio("m.mp3", 3))
        Track(kind="video").add_clip(Clip.from_image("p.jpg"))

    def test_duplicate_clip_rejected(self):
        track = Track(kind="video")
        clip = video(3)
        track.add_clip(clip)
        with self.assertRaises(ValueError):
            track.add_clip(clip)

    def test_remove_clip(self):
        track = self.make_track(1, 2)
        clip = track.clips[0]
        self.assertIs(track.remove_clip(clip.id), clip)
        self.assertEqual(len(track.clips), 1)
        with self.assertRaises(KeyError):
            track.remove_clip(clip.id)

    def test_non_ripple_uses_explicit_start(self):
        track = Track(kind="audio", ripple=False)
        track.add_clip(Clip.from_audio("m.mp3", 30, start=5.0))
        placed = track.layout()[0]
        self.assertEqual((placed.start, placed.end), (5.0, 35.0))

    def test_leaving_ripple_mode_freezes_positions(self):
        track = self.make_track(4, 6)
        track.set_ripple(False)
        self.assertEqual([c.start for c in track.clips], [0, 4])
        track.clips[1].start = 20
        self.assertEqual(track.layout()[1].start, 20)

    def test_clip_at(self):
        track = self.make_track(4, 6)
        self.assertIs(track.clip_at(1).clip, track.clips[0])
        self.assertIs(track.clip_at(4).clip, track.clips[1])
        self.assertIsNone(track.clip_at(10))

    def test_dict_round_trip(self):
        track = self.make_track(4, 6)
        track.clips[1].transition_in = Transition("fade", 1)
        again = Track.from_dict(track.to_dict())
        self.assertEqual(again, track)


if __name__ == "__main__":
    unittest.main()
