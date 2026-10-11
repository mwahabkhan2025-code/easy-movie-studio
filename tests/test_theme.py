import unittest

from easy_movie_studio.ui.theme import COLORS, stylesheet


class ThemeTests(unittest.TestCase):
    def test_all_placeholders_are_filled(self):
        qss = stylesheet()
        self.assertNotIn("$", qss)
        self.assertIn(COLORS["file_blue"], qss)

    def test_braces_are_balanced(self):
        qss = stylesheet()
        self.assertEqual(qss.count("{"), qss.count("}"))

    def test_expected_widgets_are_styled(self):
        qss = stylesheet()
        for name in ("#fileTab", "#ribbonTab", "#contextHeader", "#ribbonLarge",
                     "#galleryTile", "#fileMenu", "#workspace"):
            self.assertIn(name, qss)


if __name__ == "__main__":
    unittest.main()
