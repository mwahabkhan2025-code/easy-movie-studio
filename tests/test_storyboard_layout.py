import unittest

from easy_movie_studio.ui.storyboard_layout import hit_test, layout_clips


class LayoutTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(layout_clips([], 10, 800, 50), ([], 0.0))

    def test_width_proportional_to_duration(self):
        rects, _ = layout_clips([10, 20], 10, 1000, 50, gap=8, margin=12)
        self.assertEqual(rects[0], (12, 12, 100, 50))
        self.assertEqual(rects[1], (120, 12, 200, 50))

    def test_minimum_width(self):
        rects, _ = layout_clips([0.5], 10, 1000, 50, min_width=64)
        self.assertEqual(rects[0][2], 64)

    def test_wraps_to_next_row(self):
        rects, height = layout_clips([30, 30, 30], 10, 700, 50, gap=8, margin=12)
        self.assertEqual([r[1] for r in rects], [12, 12, 70])  # third clip wraps
        self.assertEqual(rects[2][0], 12)
        self.assertEqual(height, 70 + 50 + 12)

    def test_long_clip_is_clamped_to_row_width(self):
        rects, _ = layout_clips([1000], 10, 500, 50, margin=12)
        self.assertEqual(rects[0][2], 476)

    def test_hit_test(self):
        rects, _ = layout_clips([10, 10], 10, 1000, 50)
        self.assertEqual(hit_test(rects, 20, 20), 0)
        self.assertEqual(hit_test(rects, 130, 20), 1)
        self.assertEqual(hit_test(rects, 5, 5), -1)


if __name__ == "__main__":
    unittest.main()


class CoverRectTests(unittest.TestCase):
    def test_wide_image_into_narrow_target_crops_sides(self):
        from easy_movie_studio.ui.storyboard_layout import cover_source_rect
        x, y, w, h = cover_source_rect(200, 100, 50, 50)
        self.assertEqual((y, h), (0.0, 100))
        self.assertEqual((x, w), (50.0, 100.0))

    def test_tall_image_into_wide_target_crops_top_and_bottom(self):
        from easy_movie_studio.ui.storyboard_layout import cover_source_rect
        x, y, w, h = cover_source_rect(100, 200, 100, 50)
        self.assertEqual((x, w), (0.0, 100))
        self.assertEqual((y, h), (75.0, 50.0))

    def test_degenerate_sizes_do_not_crash(self):
        from easy_movie_studio.ui.storyboard_layout import cover_source_rect
        self.assertEqual(len(cover_source_rect(0, 0, 10, 10)), 4)


class EdgeHitTests(unittest.TestCase):
    def test_left_and_right_margins(self):
        from easy_movie_studio.ui.storyboard_layout import edge_hit
        rect = (100.0, 0.0, 50.0, 40.0)
        self.assertEqual(edge_hit(rect, 100.0), "left")
        self.assertEqual(edge_hit(rect, 106.0), "left")
        self.assertEqual(edge_hit(rect, 150.0), "right")
        self.assertEqual(edge_hit(rect, 144.0), "right")
        self.assertIsNone(edge_hit(rect, 125.0))

    def test_narrow_rect_margins_do_not_overlap_incorrectly(self):
        from easy_movie_studio.ui.storyboard_layout import edge_hit
        rect = (0.0, 0.0, 10.0, 40.0)
        self.assertEqual(edge_hit(rect, 2.0), "left")  # left check wins on tiny rects


class InsertionIndexTests(unittest.TestCase):
    def test_empty(self):
        from easy_movie_studio.ui.storyboard_layout import insertion_index
        self.assertEqual(insertion_index([], 50, 10), 0)

    def test_single_row_before_between_after(self):
        from easy_movie_studio.ui.storyboard_layout import insertion_index
        rects, _ = layout_clips([10, 10, 10], 10, 1000, 50)  # widths 100 each, gap 8
        self.assertEqual(insertion_index(rects, 5, 20), 0)      # left of first
        self.assertEqual(insertion_index(rects, 60, 20), 0)     # left half of first block
        self.assertEqual(insertion_index(rects, 90, 20), 1)     # right half of first block
        self.assertEqual(insertion_index(rects, 165, 20), 1)    # left half of second block
        self.assertEqual(insertion_index(rects, 900, 20), 3)    # well past the last block

    def test_matches_track_move_clip_semantics(self):
        """insertion_index on the *other* clips' rects should equal the index
        move_clip needs to reproduce a drag to a given visual slot."""
        from easy_movie_studio.model import Clip, Track
        from easy_movie_studio.ui.storyboard_layout import insertion_index

        track = Track(kind="video")
        for i, d in enumerate((4, 4, 4, 4)):
            track.add_clip(Clip.from_video(f"v{i}.mp4", d))
        dragged = track.clips[0].id
        durations = [c.duration for c in track.clips if c.id != dragged]
        rects, _ = layout_clips(durations, 10, 1000, 50)
        # dragging clip 0 to past the right edge of the last remaining clip (append at end)
        last = rects[-1]
        target = insertion_index(rects, last[0] + last[2] + 20, last[1] + last[3] / 2)
        track.move_clip(dragged, target)
        self.assertEqual([c.source for c in track.clips],
                         ["v1.mp4", "v2.mp4", "v3.mp4", "v0.mp4"])

    def test_second_row_point_lands_in_second_row(self):
        from easy_movie_studio.ui.storyboard_layout import insertion_index
        rects, _ = layout_clips([30, 30, 30], 10, 700, 50, gap=8, margin=12)  # third wraps
        self.assertGreater(rects[2][1], rects[0][1])  # sanity: row 2 is lower than row 1
        x_past_row2_item = rects[2][0] + rects[2][2] + 20
        y_row2 = rects[2][1] + rects[2][3] / 2
        self.assertEqual(insertion_index(rects, x_past_row2_item, y_row2), 3)
        # a point far below everything should snap to the nearest (last) row
        self.assertEqual(insertion_index(rects, x_past_row2_item, rects[2][1] + 500), 3)

    def test_point_above_everything_picks_nearest_row(self):
        from easy_movie_studio.ui.storyboard_layout import insertion_index
        rects, _ = layout_clips([10], 10, 1000, 50, margin=12)
        self.assertEqual(insertion_index(rects, 5, -100), 0)


if __name__ == "__main__":
    unittest.main()
