import unittest

from easy_movie_studio.engine.media_info import AudioStream, MediaInfo, VideoStream
from easy_movie_studio.engine.probe import probe
from easy_movie_studio.engine.properties import (aspect_text, compare_with_project, container_label,
                                       describe, format_bitrate, format_size, sections_to_text)
from easy_movie_studio.model import Clip, ProjectSettings, Transition

from .media_fixtures import MediaSet, needs_ffmpeg


def sample_info(**kw):
    video = VideoStream("h264", "High", 1280, 720, 25.0, 4_000_000, "yuv420p", 0)
    audio = AudioStream("aac", "LC", 48000, 2, "stereo", 128_000)
    base = dict(path="/videos/trip.mp4", kind="video", duration=12.5, size_bytes=6_500_000,
                modified=1_700_000_000, container="mov,mp4,m4a,3gp,3g2,mj2", bitrate=4_200_000,
                video=video, audio=audio, video_streams=1, audio_streams=1)
    base.update(kw)
    return MediaInfo(**base)


class FormattingTests(unittest.TestCase):
    def test_format_size(self):
        self.assertEqual(format_size(512), "512 bytes")
        self.assertEqual(format_size(2048), "2.0 KB")
        self.assertEqual(format_size(5 * 1024 * 1024), "5.0 MB")

    def test_format_bitrate(self):
        self.assertEqual(format_bitrate(128_000), "128 kbps")
        self.assertEqual(format_bitrate(4_200_000), "4.20 Mbps")
        self.assertEqual(format_bitrate(None), "Unknown")

    def test_aspect_text(self):
        self.assertEqual(aspect_text(1920, 1080), "16:9")
        self.assertEqual(aspect_text(640, 480), "4:3")
        self.assertEqual(aspect_text(1000, 999), "1.00:1")

    def test_container_label(self):
        self.assertEqual(container_label("mov,mp4,m4a,3gp,3g2,mj2"), "MP4")
        self.assertEqual(container_label("matroska,webm"), "Matroska (MKV/WebM)")
        self.assertEqual(container_label("weird"), "weird")


class DescribeTests(unittest.TestCase):
    def rows(self, sections, title):
        return dict(dict(sections)[title])

    def test_video_sections(self):
        sections = describe(sample_info())
        self.assertEqual([t for t, _ in sections], ["General", "Video", "Audio"])
        self.assertEqual(self.rows(sections, "General")["Name"], "trip.mp4")
        self.assertEqual(self.rows(sections, "General")["Duration"], "00:12.50")
        video = self.rows(sections, "Video")
        self.assertEqual(video["Codec"], "h264 (High)")
        self.assertEqual(video["Resolution"], "1280 \u00d7 720  (16:9)")
        self.assertEqual(video["Frame rate"], "25 fps")
        self.assertEqual(self.rows(sections, "Audio")["Channels"], "Stereo")

    def test_no_audio_and_rotation(self):
        info = sample_info(audio=None, audio_streams=0)
        info.video.rotation = 90
        sections = describe(info)
        self.assertIn("no audio", self.rows(sections, "Audio")["Audio"])
        self.assertEqual(self.rows(sections, "Video")["Resolution"], "720 \u00d7 1280  (9:16)")
        self.assertIn("Rotation flag", self.rows(sections, "Video"))

    def test_in_movie_section(self):
        clip = Clip.from_video("/videos/trip.mp4", 12.5, speed=2.0, effect="sepia",
                               transition_in=Transition("fade", 1.0))
        clip.trim(src_in=2.0, src_out=10.0)
        rows = self.rows(describe(sample_info(), clip), "In this movie")
        self.assertEqual(rows["Length in movie"], "00:04.00")
        self.assertEqual(rows["Speed"], "2x")
        self.assertEqual(rows["Effect"], "sepia")
        self.assertIn("fade", rows["Transition in"])

    def test_photo_has_no_audio_or_fps(self):
        info = sample_info(kind="image", duration=None, audio=None, audio_streams=0)
        sections = describe(info)
        self.assertEqual([t for t, _ in sections], ["General", "Photo"])
        self.assertNotIn("Frame rate", self.rows(sections, "Photo"))

    def test_technical_metadata_is_hidden(self):
        info = sample_info(metadata={"major_brand": "isom", "title": "Trip", "encoder": "x"})
        details = self.rows(describe(info), "Details")
        self.assertEqual(details, {"Title": "Trip", "Encoder": "x"})

    def test_text_export(self):
        text = sections_to_text(describe(sample_info()), ["Something differs."])
        self.assertTrue(text.startswith("! Something differs."))
        self.assertIn("  Name: trip.mp4", text)
        self.assertTrue(text.endswith("\n"))


class CompareTests(unittest.TestCase):
    def test_matching_clip_has_no_notes(self):
        info = sample_info()
        info.video.width, info.video.height, info.video.fps = 1920, 1080, 30.0
        self.assertEqual(compare_with_project(info, ProjectSettings()), [])

    def test_size_fps_rotation_and_audio_notes(self):
        info = sample_info(audio=None)
        notes = compare_with_project(info, ProjectSettings())
        self.assertEqual(len(notes), 3)  # size, fps, no audio
        self.assertIn("scaled to fit", notes[0])  # 16:9 into 16:9
        self.assertIn("25", notes[1])
        info.video.rotation = 90
        info.video.fps = 30.0
        notes = compare_with_project(info, ProjectSettings())
        self.assertTrue(any("black bars" in n for n in notes))
        self.assertTrue(any("rotated 90" in n for n in notes))


@needs_ffmpeg
class RealDescribeTests(unittest.TestCase):
    def test_describe_real_file(self):
        media = MediaSet()
        self.addCleanup(media.cleanup)
        sections = dict(describe(probe(media.video_av, use_ffprobe=False)))
        self.assertEqual(dict(sections["Video"])["Resolution"], "320 \u00d7 240  (4:3)")
        self.assertEqual(dict(sections["Audio"])["Sample rate"], "44.1 kHz")


if __name__ == "__main__":
    unittest.main()


class MetadataLabelTests(unittest.TestCase):
    def test_gps_location_tag_is_relabelled_to_avoid_clashing_with_the_folder_row(self):
        info = sample_info(metadata={"location": "+09.9092+078.1471/"})
        sections = dict(describe(info))
        general = dict(sections["General"])
        details = dict(sections["Details"])
        self.assertEqual(general["Location"], "/videos")           # the folder, unchanged
        self.assertEqual(details["GPS coordinates"], "+09.9092+078.1471/")
        self.assertNotIn("Location", details)
