import struct
import unittest

from easy_movie_studio.engine.thumbnails import ThumbnailError, extract_frame_png

from .media_fixtures import MediaSet, needs_ffmpeg


def png_size(data):
    return struct.unpack(">II", data[16:24])


@needs_ffmpeg
class ThumbnailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media = MediaSet()

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()

    def test_video_frame_has_requested_height(self):
        data = extract_frame_png(self.media.video_av, 1.0, 60)
        self.assertTrue(data.startswith(b"\x89PNG"))
        width, height = png_size(data)
        self.assertEqual(height, 60)
        self.assertEqual(width, 80)  # 320x240 scaled to height 60

    def test_photo_frame(self):
        data = extract_frame_png(self.media.photo, None, 50)
        self.assertEqual(png_size(data), (100, 50))

    def test_time_past_the_end_falls_back(self):
        data = extract_frame_png(self.media.video_av, 99.0, 40)
        self.assertEqual(png_size(data)[1], 40)

    def test_broken_file_raises(self):
        with self.assertRaises(ThumbnailError):
            extract_frame_png(self.media.broken, 0.5, 40)


if __name__ == "__main__":
    unittest.main()
