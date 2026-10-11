"""GUI test: the generated app icon. Skipped when PySide6 is not installed."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class AppIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_icon_has_multiple_non_null_sizes(self):
        from easy_movie_studio.ui.icons import app_icon
        icon = app_icon()
        sizes = icon.availableSizes()
        self.assertGreaterEqual(len(sizes), 5)
        for size in sizes:
            self.assertFalse(icon.pixmap(size).isNull())

    def test_icon_is_cached(self):
        from easy_movie_studio.ui.icons import app_icon
        self.assertIs(app_icon(), app_icon())


if __name__ == "__main__":
    unittest.main()
