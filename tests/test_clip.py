import unittest

from mmclone.model import Clip, Transition


class ClipTests(unittest.TestCase):
    def test_duration_uses_speed(self):
        clip = Clip.from_video("a.mp4", 10.0)
        self.assertEqual(clip.duration, 10.0)
        clip.update(speed=2.0)
        self.assertEqual(clip.duration, 5.0)
        clip.update(speed=0.5)
        self.assertEqual(clip.duration, 20.0)

    def test_trim_changes_duration(self):
        clip = Clip.from_video("a.mp4", 10.0)
        clip.trim(src_in=2.0, src_out=6.0)
        self.assertEqual(clip.duration, 4.0)

    def test_invalid_trim_raises_and_reverts(self):
        clip = Clip.from_video("a.mp4", 10.0)
        with self.assertRaises(ValueError):
            clip.trim(src_out=11.0)  # beyond media
        with self.assertRaises(ValueError):
            clip.trim(src_in=9.99)  # too short
        self.assertEqual((clip.src_in, clip.src_out), (0.0, 10.0))

    def test_image_default_duration(self):
        clip = Clip.from_image("p.jpg")
        self.assertEqual(clip.duration, 7.0)
        self.assertIsNone(clip.media_duration)

    def test_rotate_wraps(self):
        clip = Clip.from_video("a.mp4", 5.0)
        clip.rotate(90)
        clip.rotate(90)
        self.assertEqual(clip.rotation, 180)
        clip.rotate(-270)
        self.assertEqual(clip.rotation, 270)
        with self.assertRaises(ValueError):
            clip.rotate(45)

    def test_invalid_values_rejected(self):
        with self.assertRaises(ValueError):
            Clip(source="a.mp4", kind="text", src_out=1.0)
        clip = Clip.from_video("a.mp4", 5.0)
        for bad in ({"speed": 0}, {"speed": 100}, {"volume": -1}, {"brightness": 2},
                    {"rotation": 45}, {"fade_in": -1}):
            with self.assertRaises(ValueError):
                clip.update(**bad)
        self.assertEqual(clip.speed, 1.0)

    def test_id_is_read_only(self):
        clip = Clip.from_video("a.mp4", 5.0)
        with self.assertRaises(AttributeError):
            clip.update(id="x")

    def test_duplicate_gets_new_id_and_independent_transition(self):
        clip = Clip.from_video("a.mp4", 5.0, transition_in=Transition("fade", 1.0))
        copy = clip.duplicate()
        self.assertNotEqual(copy.id, clip.id)
        copy.transition_in.duration = 2.0
        self.assertEqual(clip.transition_in.duration, 1.0)

    def test_dict_round_trip(self):
        clip = Clip.from_video("a.mp4", 8.0, speed=2.0, effect="sepia", pan_zoom="zoom_in",
                               transition_in=Transition("wipe", 0.5))
        again = Clip.from_dict(clip.to_dict())
        self.assertEqual(again, clip)

    def test_from_dict_ignores_unknown_keys(self):
        data = Clip.from_video("a.mp4", 4.0).to_dict()
        data["future_field"] = 123
        self.assertEqual(Clip.from_dict(data).duration, 4.0)


if __name__ == "__main__":
    unittest.main()


class TitleClipTests(unittest.TestCase):
    def test_from_title_defaults(self):
        clip = Clip.from_title("/tmp/card.png", 5.0, text="Hello")
        self.assertEqual(clip.kind, "title")
        self.assertEqual(clip.duration, 5.0)
        self.assertIsNone(clip.media_duration)
        self.assertEqual(clip.text, "Hello")
        self.assertEqual(clip.text_style, "title")
        self.assertEqual(clip.text_background, "#101010")
        self.assertIsNone(clip.text_lines)

    def test_from_title_with_credits_lines(self):
        lines = [["Directed by", "A. Director"], ["Starring", "B. Actor"]]
        clip = Clip.from_title("/tmp/credits.png", 8.0, style="credits", lines=lines)
        self.assertEqual(clip.text_style, "credits")
        self.assertEqual(clip.text_lines, lines)

    def test_invalid_style_or_caption_position_rejected(self):
        clip = Clip.from_title("/tmp/c.png", 4.0)
        with self.assertRaises(ValueError):
            clip.update(text_style="subtitle")
        with self.assertRaises(ValueError):
            clip.update(caption_position="center")

    def test_duplicate_deep_copies_text_lines(self):
        lines = [["Role", "Name"]]
        clip = Clip.from_title("/tmp/c.png", 4.0, style="credits", lines=lines)
        copy = clip.duplicate()
        copy.text_lines[0][1] = "Someone else"
        self.assertEqual(clip.text_lines[0][1], "Name")  # original untouched

    def test_round_trip_through_dict(self):
        lines = [["Music by", "Composer"]]
        clip = Clip.from_title("/tmp/c.png", 6.0, text="Credits", style="credits",
                               background="#223344", lines=lines)
        again = Clip.from_dict(clip.to_dict())
        self.assertEqual(again, clip)

    def test_caption_fields_on_an_ordinary_video_clip(self):
        clip = Clip.from_video("a.mp4", 10.0, caption_text="Hello there",
                               caption_position="top")
        self.assertEqual(clip.caption_text, "Hello there")
        self.assertEqual(clip.caption_position, "top")
        clip.update(caption_text="", caption_position="bottom")
        self.assertEqual(clip.caption_text, "")


class OverlayFieldTests(unittest.TestCase):
    def test_defaults(self):
        clip = Clip.from_video("a.mp4", 5.0)
        self.assertEqual((clip.overlay_x, clip.overlay_y), (0.75, 0.75))
        self.assertEqual(clip.overlay_scale, 0.35)
        self.assertEqual(clip.opacity, 1.0)

    def test_valid_updates(self):
        clip = Clip.from_video("a.mp4", 5.0)
        clip.update(overlay_x=0.1, overlay_y=0.9, overlay_scale=0.5, opacity=0.6)
        self.assertEqual((clip.overlay_x, clip.overlay_y, clip.overlay_scale, clip.opacity),
                         (0.1, 0.9, 0.5, 0.6))

    def test_out_of_range_rejected_and_rolled_back(self):
        clip = Clip.from_video("a.mp4", 5.0)
        for bad in ({"overlay_x": 1.5}, {"overlay_y": -0.1}, {"overlay_scale": 0.01},
                    {"overlay_scale": 1.5}, {"opacity": 1.1}, {"opacity": -0.1}):
            with self.assertRaises(ValueError):
                clip.update(**bad)
        self.assertEqual(clip.overlay_scale, 0.35)
