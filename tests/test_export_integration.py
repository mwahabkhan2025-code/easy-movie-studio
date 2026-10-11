"""Runs real exports through real FFmpeg (using the tiny clips from media_fixtures)
and checks the *output* with ffprobe -- this is the strongest test we have that the
generated filter graphs are actually valid, not just plausible-looking strings."""

import os
import shutil
import tempfile
import unittest

from easy_movie_studio.engine.export import ExportRunError, run_export
from easy_movie_studio.engine.export_plan import ExportSettings, build_export_plan, resolve_settings
from easy_movie_studio.engine.probe import probe
from easy_movie_studio.model import Clip, Project, Transition
from easy_movie_studio.model.track import TRACK_AUDIO

from .media_fixtures import MediaSet, needs_ffmpeg


@needs_ffmpeg
class ExportIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media = MediaSet()

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()

    def setUp(self):
        self.out_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.out_dir, ignore_errors=True)

    def out(self, name):
        return os.path.join(self.out_dir, name)

    def export(self, project, name, settings=None, silent_sources=None):
        settings = settings or ExportSettings(width=160, height=120, fps=25, sample_rate=48000)
        path = self.out(name)
        plan = build_export_plan(project, path, settings, silent_sources)
        progress = []
        run_export(plan, on_progress=progress.append)
        self.assertTrue(os.path.isfile(path), "export did not produce a file")
        self.assertGreater(os.path.getsize(path), 0)
        self.assertTrue(progress, "no progress was reported")
        self.assertLessEqual(max(progress), 1.0)
        return path

    def test_single_clip_round_trip(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video(self.media.video_av, 2.0))
        path = self.export(project, "single.mp4")
        info = probe(path)
        self.assertEqual((info.video.width, info.video.height), (160, 120))
        self.assertAlmostEqual(info.duration, 2.0, delta=0.3)
        self.assertTrue(info.has_audio)

    def test_two_clips_hard_cut_duration_and_size(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video(self.media.video_av, 2.0))
        project.main_track.add_clip(Clip.from_video(self.media.video_silent, 1.0))
        # video_silent.mp4 genuinely has no audio track -- must be declared, or FFmpeg
        # correctly refuses to reference a stream that doesn't exist.
        path = self.export(project, "cut.mp4", silent_sources={self.media.video_silent})
        info = probe(path)
        self.assertAlmostEqual(info.duration, 3.0, delta=0.3)
        self.assertEqual((info.video.width, info.video.height), (160, 120))

    def test_transition_shortens_output_by_the_overlap(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video(self.media.video_av, 2.0))
        second = Clip.from_video(self.media.video_silent, 1.0,
                                 transition_in=Transition("fade", 0.5))
        project.main_track.add_clip(second)
        path = self.export(project, "fade.mp4", silent_sources={self.media.video_silent})
        info = probe(path)
        self.assertAlmostEqual(info.duration, 2.5, delta=0.3)  # 2 + 1 - 0.5

    def test_photo_clip_produces_video_with_silent_audio(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_image(self.media.photo, 1.5))
        path = self.export(project, "photo.mp4")
        info = probe(path)
        self.assertAlmostEqual(info.duration, 1.5, delta=0.3)
        self.assertTrue(info.has_audio)  # silence track still gives a playable audio stream

    def test_mixed_photo_and_video(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_image(self.media.photo, 1.0))
        project.main_track.add_clip(Clip.from_video(self.media.video_av, 2.0))
        path = self.export(project, "mixed.mp4")
        info = probe(path)
        self.assertAlmostEqual(info.duration, 3.0, delta=0.3)

    def test_silent_video_source_is_handled(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video(self.media.video_silent, 1.0))
        path = self.export(project, "silent.mp4", silent_sources={self.media.video_silent})
        info = probe(path)
        self.assertTrue(info.has_audio)  # got a silence track instead of failing

    def test_rotation_is_baked_into_the_output(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video(self.media.video_av, 2.0, rotation=90))
        path = self.export(project, "rot.mp4",
                           settings=ExportSettings(width=120, height=160, fps=25,
                                                   sample_rate=48000))
        info = probe(path)
        self.assertEqual((info.video.width, info.video.height), (120, 160))

    def test_speed_change_shortens_duration(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video(self.media.video_av, 2.0, speed=2.0))
        path = self.export(project, "fast.mp4")
        info = probe(path)
        self.assertAlmostEqual(info.duration, 1.0, delta=0.25)

    def test_music_track_is_present_in_output(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video(self.media.video_silent, 2.0))
        project.tracks[1].add_clip(Clip.from_audio(self.media.tone, 1.0, start=0.5))
        path = self.export(project, "music.mp4", silent_sources={self.media.video_silent})
        info = probe(path)
        self.assertTrue(info.has_audio)
        self.assertAlmostEqual(info.duration, 2.0, delta=0.3)

    def test_audio_only_export(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video(self.media.video_av, 2.0))
        settings = resolve_settings(project, "audio")
        path = self.out("audio.mp3")
        plan = build_export_plan(project, path, settings)
        run_export(plan)
        info = probe(path)
        self.assertEqual(info.kind, "audio")
        self.assertAlmostEqual(info.duration, 2.0, delta=0.3)

    def test_gif_export(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video(self.media.video_av, 1.0))
        settings = ExportSettings(width=160, height=120, fps=10, output_kind="gif",
                                  gif_width=80, gif_fps=8)
        path = self.out("clip.gif")
        plan = build_export_plan(project, path, settings)
        run_export(plan)
        self.assertTrue(os.path.isfile(path))
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(3), b"GIF")

    def test_bad_source_file_raises_export_run_error_not_a_crash(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video(self.media.broken, 2.0))
        settings = ExportSettings(width=160, height=120, fps=25, sample_rate=48000)
        plan = build_export_plan(project, self.out("bad.mp4"), settings)
        with self.assertRaises(ExportRunError) as ctx:
            run_export(plan)
        self.assertTrue(ctx.exception.log_tail)
        self.assertFalse(os.path.exists(self.out("bad.mp4")))  # no partial file left behind

    def test_cancel_stops_and_cleans_up(self):
        project = Project.new()
        for _ in range(4):
            project.main_track.add_clip(Clip.from_video(self.media.video_av, 2.0))
        settings = ExportSettings(width=160, height=120, fps=25, sample_rate=48000,
                                  speed_preset="veryslow", crf=10)
        path = self.out("cancelled.mp4")
        plan = build_export_plan(project, path, settings)
        handles = []
        with self.assertRaises(ExportRunError):
            run_export(plan, on_handle=lambda h: (handles.append(h), h.cancel()))
        self.assertTrue(handles[0].cancelled)
        self.assertFalse(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()


@needs_ffmpeg
class TitleCreditsCaptionExportTests(unittest.TestCase):
    """Real renders, real FFmpeg, real ffprobe checks -- same rigor as the rest of export."""

    @classmethod
    def setUpClass(cls):
        cls.media = MediaSet()

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()

    def setUp(self):
        self.out_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.out_dir, ignore_errors=True)
        from easy_movie_studio.engine import titles
        self.addCleanup(shutil.rmtree, titles.CACHE_DIR, ignore_errors=True)

    def out(self, name):
        return os.path.join(self.out_dir, name)

    def test_title_card_then_video(self):
        from easy_movie_studio.engine.titles import render_title_png
        project = Project.new()
        settings = ExportSettings(width=160, height=120, fps=25, sample_rate=48000)
        card = render_title_png("My Movie", settings.width, settings.height)
        project.main_track.add_clip(Clip.from_title(card, 1.0, text="My Movie"))
        project.main_track.add_clip(Clip.from_video(self.media.video_av, 2.0))
        path = self.out("title.mp4")
        plan = build_export_plan(project, path, settings)
        run_export(plan)
        info = probe(path)
        self.assertAlmostEqual(info.duration, 3.0, delta=0.3)
        self.assertEqual((info.video.width, info.video.height), (160, 120))

    def test_credits_card_at_the_end(self):
        from easy_movie_studio.engine.titles import render_title_png
        project = Project.new()
        settings = ExportSettings(width=160, height=120, fps=25, sample_rate=48000)
        project.main_track.add_clip(Clip.from_video(self.media.video_av, 2.0))
        lines = [["Directed by", "A. Tester"], ["Music by", "B. Composer"]]
        card = render_title_png("", settings.width, settings.height, style="credits",
                                lines=lines)
        project.main_track.add_clip(Clip.from_title(card, 1.5, style="credits", lines=lines))
        path = self.out("credits.mp4")
        plan = build_export_plan(project, path, settings)
        run_export(plan)
        info = probe(path)
        self.assertAlmostEqual(info.duration, 3.5, delta=0.3)

    def test_captioned_clip_exports_successfully(self):
        project = Project.new()
        settings = ExportSettings(width=160, height=120, fps=25, sample_rate=48000)
        project.main_track.add_clip(Clip.from_video(self.media.video_av, 2.0,
                                                     caption_text="Hello, world!",
                                                     caption_position="bottom"))
        path = self.out("caption.mp4")
        plan = build_export_plan(project, path, settings)
        run_export(plan)  # the real test: FFmpeg must accept the drawtext filter and succeed
        info = probe(path)
        self.assertAlmostEqual(info.duration, 2.0, delta=0.3)

    def test_caption_with_quotes_and_colons_does_not_break_ffmpeg(self):
        project = Project.new()
        settings = ExportSettings(width=160, height=120, fps=25, sample_rate=48000)
        tricky = "It's 10:30 — \"go!\""
        project.main_track.add_clip(Clip.from_video(self.media.video_av, 1.0,
                                                     caption_text=tricky))
        path = self.out("tricky.mp4")
        plan = build_export_plan(project, path, settings)
        run_export(plan)
        self.assertTrue(os.path.isfile(path))

    def test_full_movie_title_captioned_clip_and_credits(self):
        from easy_movie_studio.engine.titles import render_title_png
        project = Project.new()
        settings = ExportSettings(width=160, height=120, fps=25, sample_rate=48000)
        title_card = render_title_png("Family Trip", settings.width, settings.height)
        project.main_track.add_clip(Clip.from_title(title_card, 1.0, text="Family Trip"))
        project.main_track.add_clip(Clip.from_video(self.media.video_av, 2.0,
                                                     caption_text="At the lake"))
        credits_lines = [["Filmed by", "Someone"]]
        credits_card = render_title_png("", settings.width, settings.height, style="credits",
                                        lines=credits_lines)
        project.main_track.add_clip(Clip.from_title(credits_card, 1.0, style="credits",
                                                    lines=credits_lines))
        path = self.out("full.mp4")
        plan = build_export_plan(project, path, settings)
        run_export(plan)
        info = probe(path)
        self.assertAlmostEqual(info.duration, 4.0, delta=0.3)
        self.assertTrue(info.has_audio)  # title/credits contribute silence, video contributes tone


if __name__ == "__main__":
    unittest.main()


@needs_ffmpeg
class AudioMixExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media = MediaSet()

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()

    def setUp(self):
        self.out_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.out_dir, ignore_errors=True)

    def test_project_level_volume_and_ducking_export_successfully(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video(self.media.video_av, 2.0))
        project.tracks[1].add_clip(Clip.from_audio(self.media.tone, 1.0))
        project.settings.video_volume = 0.7
        project.settings.music_volume = 0.5
        project.settings.duck_music = True
        settings = ExportSettings(width=160, height=120, fps=25, sample_rate=48000,
                                  video_volume=project.settings.video_volume,
                                  music_volume=project.settings.music_volume,
                                  duck_music=project.settings.duck_music)
        path = os.path.join(self.out_dir, "mix.mp4")
        plan = build_export_plan(project, path, settings)
        run_export(plan)
        info = probe(path)
        self.assertTrue(info.has_audio)
        self.assertAlmostEqual(info.duration, 2.0, delta=0.3)


if __name__ == "__main__":
    unittest.main()


@needs_ffmpeg
class OverlayCompositingVisualTests(unittest.TestCase):
    """Solid-color clips + real pixel sampling: this actually confirms the overlay shows
    up in the right place at the right time, not just that FFmpeg didn't error out."""

    @classmethod
    def setUpClass(cls):
        from easy_movie_studio.engine.tools import find_ffmpeg, run_tool
        cls.ffmpeg = find_ffmpeg()
        cls.dir = tempfile.mkdtemp()
        cls.red = os.path.join(cls.dir, "red.mp4")
        cls.blue = os.path.join(cls.dir, "blue.mp4")
        for path, color in ((cls.red, "red"), (cls.blue, "blue")):
            result = run_tool([cls.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                              f"color=c={color}:s=320x240:d=4:r=10", "-f", "lavfi", "-i",
                              "anullsrc=channel_layout=stereo:sample_rate=48000", "-shortest",
                              "-c:v", "mpeg4", "-c:a", "aac", path])
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        self.out_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.out_dir, ignore_errors=True)

    def sample_pixel(self, video_path, time, x, y):
        from easy_movie_studio.engine.thumbnails import extract_frame_png
        data = extract_frame_png(video_path, time, 240)
        from PIL import Image
        import io
        image = Image.open(io.BytesIO(data)).convert("RGB")
        return image.getpixel((x, y))

    def is_reddish(self, rgb):
        r, g, b = rgb
        return r > 150 and g < 100 and b < 100

    def is_blueish(self, rgb):
        r, g, b = rgb
        return b > 150 and r < 100 and g < 100

    def test_overlay_appears_at_its_position_and_not_outside_its_time_window(self):
        project = Project.new()
        project.settings.width, project.settings.height = 320, 240
        project.main_track.add_clip(Clip.from_video(self.red, 4.0))
        overlay_track = project.add_track("video", "Overlay")
        # overlay centered at (0.75, 0.75) i.e. bottom-right quadrant, visible from t=1 to t=3
        overlay_track.add_clip(Clip.from_video(self.blue, 2.0, start=1.0, overlay_x=0.75,
                                               overlay_y=0.75, overlay_scale=0.4, opacity=1.0))
        settings = ExportSettings(width=320, height=240, fps=10, sample_rate=48000)
        path = os.path.join(self.out_dir, "composite.mp4")
        plan = build_export_plan(project, path, settings)
        run_export(plan)

        # the overlay box is centered at (0.75*320, 0.75*240)=(240,180), scale 0.4 ->
        # 128x96, so it spans x:176-304, y:132-228. (290,200) is safely inside it.
        overlay_point = (290, 200)

        # top-left corner should always be the base (red), overlay never reaches there
        self.assertTrue(self.is_reddish(self.sample_pixel(path, 2.0, 10, 10)))
        # inside the overlay box, DURING the overlay's window -> blue
        self.assertTrue(self.is_blueish(self.sample_pixel(path, 2.0, *overlay_point)))
        # same point, BEFORE the overlay starts -> still red (time-gating works)
        self.assertTrue(self.is_reddish(self.sample_pixel(path, 0.3, *overlay_point)))
        # same point, AFTER the overlay ends -> red again
        self.assertTrue(self.is_reddish(self.sample_pixel(path, 3.7, *overlay_point)))

    def test_overlay_position_moves_the_box(self):
        project = Project.new()
        project.settings.width, project.settings.height = 320, 240
        project.main_track.add_clip(Clip.from_video(self.red, 3.0))
        overlay_track = project.add_track("video", "Overlay")
        # this time centered top-left (0.15, 0.15)
        overlay_track.add_clip(Clip.from_video(self.blue, 3.0, overlay_x=0.15, overlay_y=0.15,
                                               overlay_scale=0.3))
        settings = ExportSettings(width=320, height=240, fps=10, sample_rate=48000)
        path = os.path.join(self.out_dir, "topleft.mp4")
        run_export(build_export_plan(project, path, settings))
        self.assertTrue(self.is_blueish(self.sample_pixel(path, 1.5, 15, 15)))
        self.assertTrue(self.is_reddish(self.sample_pixel(path, 1.5, 300, 230)))

    def test_opacity_blends_rather_than_fully_covers(self):
        project = Project.new()
        project.settings.width, project.settings.height = 320, 240
        project.main_track.add_clip(Clip.from_video(self.red, 3.0))
        overlay_track = project.add_track("video", "Overlay")
        overlay_track.add_clip(Clip.from_video(self.blue, 3.0, overlay_x=0.5, overlay_y=0.5,
                                               overlay_scale=0.8, opacity=0.5))
        settings = ExportSettings(width=320, height=240, fps=10, sample_rate=48000)
        path = os.path.join(self.out_dir, "blend.mp4")
        run_export(build_export_plan(project, path, settings))
        r, g, b = self.sample_pixel(path, 1.5, 160, 120)
        # a 50/50 red-blue blend should land roughly in between on both channels,
        # clearly neither a pure red nor a pure blue reading
        self.assertFalse(self.is_reddish((r, g, b)))
        self.assertFalse(self.is_blueish((r, g, b)))
        self.assertGreater(r, 60)
        self.assertGreater(b, 60)

    def test_two_overlay_clips_both_composite(self):
        project = Project.new()
        project.settings.width, project.settings.height = 320, 240
        project.main_track.add_clip(Clip.from_video(self.red, 4.0))
        overlay_track = project.add_track("video", "Overlay")
        overlay_track.add_clip(Clip.from_video(self.blue, 2.0, start=0.0, overlay_x=0.15,
                                               overlay_y=0.15, overlay_scale=0.3))
        overlay_track.add_clip(Clip.from_video(self.blue, 2.0, start=2.0, overlay_x=0.85,
                                               overlay_y=0.85, overlay_scale=0.3))
        settings = ExportSettings(width=320, height=240, fps=10, sample_rate=48000)
        path = os.path.join(self.out_dir, "two.mp4")
        run_export(build_export_plan(project, path, settings))
        self.assertTrue(self.is_blueish(self.sample_pixel(path, 0.5, 15, 15)))
        self.assertTrue(self.is_blueish(self.sample_pixel(path, 3.0, 300, 230)))

    def test_overlay_clip_contributes_its_own_audio(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video(self.red, 3.0))
        overlay_track = project.add_track("video", "Overlay")
        overlay_track.add_clip(Clip.from_video(self.blue, 2.0, start=0.5))
        settings = ExportSettings(width=160, height=120, fps=10, sample_rate=48000)
        path = os.path.join(self.out_dir, "ovaudio.mp4")
        run_export(build_export_plan(project, path, settings))
        info = probe(path)
        self.assertTrue(info.has_audio)


if __name__ == "__main__":
    unittest.main()


@needs_ffmpeg
class PanZoomVisualTests(unittest.TestCase):
    """Real pixel sampling (same rigor as OverlayCompositingVisualTests above): proves the
    zoompan filter actually animates across the clip, not just that export didn't error."""

    @classmethod
    def setUpClass(cls):
        from easy_movie_studio.engine.tools import find_ffmpeg, run_tool
        cls.ffmpeg = find_ffmpeg()
        cls.dir = tempfile.mkdtemp()

        # Blue background with a red box covering the center ~84% (an 8% blue border all
        # the way around) -- at zoom=1.25 (zoom_in/zoom_out's final zoom) a 10% border is
        # cropped away, so corner pixels flip from blue (border still visible) to red
        # (border fully cropped out) once zoomed all the way in.
        cls.bordered = os.path.join(cls.dir, "bordered.png")
        result = run_tool([cls.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                          "color=c=blue:s=400x300",
                          "-vf", "drawbox=x=iw*0.08:y=ih*0.08:w=iw*0.84:h=ih*0.84:"
                                 "color=red:t=fill",
                          "-frames:v", "1", cls.bordered])
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode())

        # Left half green, right half yellow -- for pan_left/pan_right, which hold zoom
        # fixed and just slide the crop window sideways.
        cls.split = os.path.join(cls.dir, "split.png")
        result = run_tool([cls.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                          "color=c=green:s=400x300",
                          "-vf", "drawbox=x=iw/2:y=0:w=iw/2:h=ih:color=yellow:t=fill",
                          "-frames:v", "1", cls.split])
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode())

        # Top half magenta, bottom half cyan -- for pan_up/pan_down.
        cls.split_vertical = os.path.join(cls.dir, "split_vertical.png")
        result = run_tool([cls.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                          "color=c=magenta:s=400x300",
                          "-vf", "drawbox=x=0:y=ih/2:w=iw:h=ih/2:color=cyan:t=fill",
                          "-frames:v", "1", cls.split_vertical])
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        self.out_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.out_dir, ignore_errors=True)

    def corner_pixel(self, video_path, time):
        from easy_movie_studio.engine.thumbnails import extract_frame_png
        from PIL import Image
        import io
        data = extract_frame_png(video_path, time, 240)
        image = Image.open(io.BytesIO(data)).convert("RGB")
        return image.getpixel((2, 2))

    def center_pixel(self, video_path, time):
        # Near the output's own edges, a modest pan at a modest zoom never swings far
        # enough to cross the left/right color boundary (the crop window is still wide
        # relative to how far it can slide) -- the center point travels much further
        # across the source per pixel of output, so it's the reliable place to sample.
        from easy_movie_studio.engine.thumbnails import extract_frame_png
        from PIL import Image
        import io
        data = extract_frame_png(video_path, time, 240)
        image = Image.open(io.BytesIO(data)).convert("RGB")
        return image.getpixel((image.width // 2, image.height // 2))

    def is_reddish(self, rgb):
        r, g, b = rgb
        return r > 150 and g < 100 and b < 100

    def is_blueish(self, rgb):
        r, g, b = rgb
        return b > 150 and r < 100 and g < 100

    def is_greenish(self, rgb):
        r, g, b = rgb
        return g > 120 and r < 120 and b < 120

    def is_yellowish(self, rgb):
        r, g, b = rgb
        return r > 150 and g > 150 and b < 120

    def is_magentaish(self, rgb):
        r, g, b = rgb
        return r > 150 and b > 150 and g < 120

    def is_cyanish(self, rgb):
        r, g, b = rgb
        return g > 150 and b > 150 and r < 120

    def export(self, clip, name):
        project = Project.new()
        project.settings.width, project.settings.height = 400, 300
        project.main_track.add_clip(clip)
        settings = ExportSettings(width=400, height=300, fps=10, sample_rate=48000)
        path = os.path.join(self.out_dir, name)
        run_export(build_export_plan(project, path, settings))
        return path

    def test_zoom_in_crops_the_border_away_by_the_end(self):
        clip = Clip.from_image(self.bordered, 3.0, pan_zoom="zoom_in")
        path = self.export(clip, "zoom_in.mp4")
        self.assertTrue(self.is_blueish(self.corner_pixel(path, 0.05)),
                        "corner should still show the border at the very start")
        self.assertTrue(self.is_reddish(self.corner_pixel(path, 2.9)),
                        "corner should be zoomed past the border by the end")

    def test_zoom_out_is_the_reverse_of_zoom_in(self):
        clip = Clip.from_image(self.bordered, 3.0, pan_zoom="zoom_out")
        path = self.export(clip, "zoom_out.mp4")
        self.assertTrue(self.is_reddish(self.corner_pixel(path, 0.05)),
                        "corner should start already zoomed past the border")
        self.assertTrue(self.is_blueish(self.corner_pixel(path, 2.9)),
                        "corner should show the border again by the end")

    def test_pan_left_slides_the_view_from_right_to_left(self):
        clip = Clip.from_image(self.split, 3.0, pan_zoom="pan_left")
        path = self.export(clip, "pan_left.mp4")
        self.assertTrue(self.is_yellowish(self.center_pixel(path, 0.05)),
                        "pan_left starts framed toward the right (yellow) side")
        self.assertTrue(self.is_greenish(self.center_pixel(path, 2.9)),
                        "pan_left ends framed on the left (green) side")

    def test_pan_right_is_the_reverse_of_pan_left(self):
        clip = Clip.from_image(self.split, 3.0, pan_zoom="pan_right")
        path = self.export(clip, "pan_right.mp4")
        self.assertTrue(self.is_greenish(self.center_pixel(path, 0.05)),
                        "pan_right starts framed toward the left (green) side")
        self.assertTrue(self.is_yellowish(self.center_pixel(path, 2.9)),
                        "pan_right ends framed toward the right (yellow) side")

    def test_pan_up_slides_the_view_from_bottom_to_top(self):
        clip = Clip.from_image(self.split_vertical, 3.0, pan_zoom="pan_up")
        path = self.export(clip, "pan_up.mp4")
        self.assertTrue(self.is_cyanish(self.center_pixel(path, 0.05)),
                        "pan_up starts framed toward the bottom (cyan) half")
        self.assertTrue(self.is_magentaish(self.center_pixel(path, 2.9)),
                        "pan_up ends framed on the top (magenta) half")

    def test_pan_down_is_the_reverse_of_pan_up(self):
        clip = Clip.from_image(self.split_vertical, 3.0, pan_zoom="pan_down")
        path = self.export(clip, "pan_down.mp4")
        self.assertTrue(self.is_magentaish(self.center_pixel(path, 0.05)),
                        "pan_down starts framed toward the top (magenta) half")
        self.assertTrue(self.is_cyanish(self.center_pixel(path, 2.9)),
                        "pan_down ends framed on the bottom (cyan) half")
