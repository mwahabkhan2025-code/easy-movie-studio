import unittest

from easy_movie_studio.util import format_time


class FormatTimeTests(unittest.TestCase):
    def test_matches_movie_maker_clock(self):
        self.assertEqual(format_time(0), "00:00.00")
        self.assertEqual(format_time(23.7), "00:23.70")
        self.assertEqual(format_time(75.05), "01:15.05")

    def test_hours_and_negative(self):
        self.assertEqual(format_time(3725.5), "1:02:05.50")
        self.assertEqual(format_time(-3), "00:00.00")

    def test_rounding_carries_over(self):
        self.assertEqual(format_time(59.999), "01:00.00")


if __name__ == "__main__":
    unittest.main()
