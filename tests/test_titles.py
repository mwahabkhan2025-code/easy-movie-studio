import os
import shutil
import unittest

from easy_movie_studio.engine.titles import (TitleRenderError, find_font_path, render_title_png,
                                   resolve_background)


def pixel_variance(path):
    from PIL import Image
    import statistics
    image = Image.open(path).convert("L")
    pixels = list(image.tobytes())
    return statistics.pvariance(pixels)


class ResolveBackgroundTests(unittest.TestCase):
    def test_named_presets(self):
        self.assertEqual(resolve_background("Black"), "#101010")
        self.assertEqual(resolve_background("DARK BLUE"), "#0e1a33")

    def test_hex_passes_through(self):
        self.assertEqual(resolve_background("#abcdef"), "#abcdef")


class RenderTitleTests(unittest.TestCase):
    def setUp(self):
        from easy_movie_studio.engine import titles
        self.addCleanup(shutil.rmtree, titles.CACHE_DIR, ignore_errors=True)

    def test_renders_a_png_of_the_right_size(self):
        path = render_title_png("Hello World", 320, 180)
        self.assertTrue(path.endswith(".png"))
        self.assertTrue(os.path.isfile(path))
        from PIL import Image
        with Image.open(path) as image:
            self.assertEqual(image.size, (320, 180))

    def test_text_actually_appears_not_a_blank_card(self):
        path = render_title_png("Some Title Text", 320, 180)
        self.assertGreater(pixel_variance(path), 10)  # a blank card would be ~0

    def test_empty_text_does_not_crash_and_is_blank(self):
        path = render_title_png("", 200, 100)
        self.assertTrue(os.path.isfile(path))
        self.assertLess(pixel_variance(path), 5)  # nothing drawn -> near-uniform

    def test_long_text_wraps_without_crashing(self):
        long_text = "This is a fairly long title that should wrap across several lines " * 3
        path = render_title_png(long_text, 320, 180)
        self.assertTrue(os.path.isfile(path))

    def test_caching_reuses_the_same_file_for_identical_input(self):
        path1 = render_title_png("Same text", 320, 180, background="#112233")
        mtime1 = os.path.getmtime(path1)
        path2 = render_title_png("Same text", 320, 180, background="#112233")
        self.assertEqual(path1, path2)
        self.assertEqual(mtime1, os.path.getmtime(path2))

    def test_different_input_gives_different_files(self):
        path1 = render_title_png("Text A", 320, 180)
        path2 = render_title_png("Text B", 320, 180)
        path3 = render_title_png("Text A", 320, 180, background="#ff0000")
        path4 = render_title_png("Text A", 640, 360)
        self.assertEqual(len({path1, path2, path3, path4}), 4)

    def test_credits_style_with_role_name_pairs(self):
        lines = [["Directed by", "A. Director"], ["Starring", "B. Actor"]]
        path = render_title_png("", 400, 400, style="credits", lines=lines)
        self.assertGreater(pixel_variance(path), 10)

    def test_credits_style_with_no_lines_falls_back_gracefully(self):
        path = render_title_png("", 200, 100, style="credits", lines=None)
        self.assertTrue(os.path.isfile(path))  # should not crash

    def test_invalid_background_color_raises_a_clear_error(self):
        with self.assertRaises(TitleRenderError):
            render_title_png("Hi", 100, 100, background="not-a-color")

    def test_tiny_dimensions_are_clamped_not_crashed(self):
        path = render_title_png("X", 0, -5)
        from PIL import Image
        with Image.open(path) as image:
            self.assertGreaterEqual(image.size[0], 16)
            self.assertGreaterEqual(image.size[1], 16)

    def test_find_font_path_returns_a_real_file_or_none(self):
        path = find_font_path(bold=True)
        if path is not None:
            self.assertTrue(os.path.isfile(path))


if __name__ == "__main__":
    unittest.main()
