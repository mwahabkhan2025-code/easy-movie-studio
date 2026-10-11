import unittest

from mmclone.ui.timeline_layout import (LEFT_MARGIN, ROW_GAP, ROW_HEIGHT, RULER_HEIGHT,
                                        collect_snap_anchors, row_at_y, row_top, snap_time,
                                        time_to_x, x_to_time)


class TimeXConversionTests(unittest.TestCase):
    def test_round_trip(self):
        x = time_to_x(5.0, pps=20.0)
        self.assertAlmostEqual(x_to_time(x, pps=20.0), 5.0)

    def test_zero_time_at_left_margin(self):
        self.assertEqual(time_to_x(0.0, 20.0), LEFT_MARGIN)

    def test_scroll_offsets_both_directions(self):
        x = time_to_x(10.0, pps=10.0, scroll=4.0)
        self.assertAlmostEqual(x_to_time(x, pps=10.0, scroll=4.0), 10.0)

    def test_x_to_time_never_negative(self):
        self.assertEqual(x_to_time(0.0, pps=10.0), 0.0)
        self.assertEqual(x_to_time(-500.0, pps=10.0), 0.0)

    def test_zero_pps_does_not_crash(self):
        self.assertEqual(x_to_time(100.0, pps=0.0), 0.0)


class RowLayoutTests(unittest.TestCase):
    def test_row_top_increases_by_row_height_plus_gap(self):
        self.assertEqual(row_top(0), RULER_HEIGHT)
        self.assertEqual(row_top(1), RULER_HEIGHT + ROW_HEIGHT + ROW_GAP)
        self.assertEqual(row_top(2), RULER_HEIGHT + 2 * (ROW_HEIGHT + ROW_GAP))

    def test_row_at_y_in_ruler_is_none(self):
        self.assertIsNone(row_at_y(5.0, track_count=3))

    def test_row_at_y_finds_correct_row(self):
        self.assertEqual(row_at_y(RULER_HEIGHT + 1, 3), 0)
        self.assertEqual(row_at_y(row_top(1) + 1, 3), 1)
        self.assertEqual(row_at_y(row_top(2) + ROW_HEIGHT - 1, 3), 2)

    def test_row_at_y_in_a_gap_is_none(self):
        gap_y = row_top(0) + ROW_HEIGHT + ROW_GAP / 2
        self.assertIsNone(row_at_y(gap_y, 3))

    def test_row_at_y_beyond_last_track_is_none(self):
        self.assertIsNone(row_at_y(row_top(5), track_count=3))

    def test_no_tracks_is_always_none(self):
        self.assertIsNone(row_at_y(RULER_HEIGHT + 5, track_count=0))


class SnapTimeTests(unittest.TestCase):
    def test_snaps_to_nearest_anchor_within_threshold(self):
        self.assertEqual(snap_time(5.1, [5.0, 10.0], threshold_seconds=0.3), 5.0)

    def test_outside_threshold_keeps_candidate(self):
        self.assertEqual(snap_time(5.5, [5.0, 10.0], threshold_seconds=0.3), 5.5)

    def test_picks_the_closest_of_several_anchors(self):
        self.assertEqual(snap_time(7.4, [5.0, 7.5, 10.0], threshold_seconds=1.0), 7.5)

    def test_no_anchors_keeps_candidate(self):
        self.assertEqual(snap_time(3.0, [], threshold_seconds=1.0), 3.0)

    def test_never_returns_negative(self):
        self.assertEqual(snap_time(-0.05, [0.0], threshold_seconds=0.5), 0.0)

    def test_exact_match_snaps(self):
        self.assertEqual(snap_time(5.0, [5.0], threshold_seconds=0.1), 5.0)


class CollectSnapAnchorsTests(unittest.TestCase):
    def test_flattens_and_dedupes_across_tracks(self):
        tracks = [[(0.0, 4.0), (4.0, 9.0)], [(2.0, 6.0)]]
        anchors = collect_snap_anchors(tracks)
        self.assertEqual(anchors, [0.0, 2.0, 4.0, 6.0, 9.0])

    def test_always_includes_zero(self):
        self.assertIn(0.0, collect_snap_anchors([[(5.0, 8.0)]]))

    def test_extra_anchors_included(self):
        anchors = collect_snap_anchors([], extra=[3.5, 12.0])
        self.assertEqual(anchors, [0.0, 3.5, 12.0])

    def test_skips_the_dragged_clip_s_own_span(self):
        tracks = [[(0.0, 4.0), (4.0, 9.0)]]
        anchors = collect_snap_anchors(tracks, skip_clip_span=(4.0, 9.0))
        self.assertEqual(anchors, [0.0, 4.0])  # 9.0 excluded, but 4.0 survives (shared edge)

    def test_empty_tracks_still_has_zero(self):
        self.assertEqual(collect_snap_anchors([]), [0.0])


if __name__ == "__main__":
    unittest.main()
