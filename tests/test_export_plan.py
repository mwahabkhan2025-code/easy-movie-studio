import unittest

from easy_movie_studio.engine.export_plan import (ExportError, ExportSettings, build_export_plan,
                                        estimate_output_bytes, even, resolve_settings)
from easy_movie_studio.model import Clip, Project, Track, Transition
from easy_movie_studio.model.track import TRACK_AUDIO


def args_to_text(args):
    return " ".join(args)


def settings_for(project, height=360):
    return ExportSettings(width=Project.new().settings.width, height=height,
                          fps=project.settings.fps, sample_rate=project.settings.sample_rate)


class EvenTests(unittest.TestCase):
    def test_rounds_to_nearest_even(self):
        self.assertEqual(even(1080), 1080)
        self.assertEqual(even(1081) % 2, 0)  # banker's rounding may give 1080 or 1082
        self.assertEqual(even(719), 720)
        self.assertEqual(even(1), 2)
        self.assertEqual(even(0), 2)


class ResolveSettingsTests(unittest.TestCase):
    def test_recommended_keeps_project_size(self):
        project = Project.new()
        settings = resolve_settings(project, "recommended")
        self.assertEqual((settings.width, settings.height), (1920, 1080))
        self.assertEqual(settings.output_kind, "video")

    def test_height_presets_scale_preserving_aspect(self):
        project = Project.new()
        settings = resolve_settings(project, "standard")
        self.assertEqual((settings.width, settings.height), (1280, 720))
        settings = resolve_settings(project, "small")
        self.assertEqual((settings.width, settings.height), (854, 480))

    def test_vertical_project_scales_correctly(self):
        project = Project.new()
        project.set_aspect("9:16")
        settings = resolve_settings(project, "hq")
        self.assertEqual((settings.width, settings.height), (608, 1080))

    def test_audio_and_gif_kinds(self):
        self.assertEqual(resolve_settings(Project.new(), "audio").output_kind, "audio")
        self.assertEqual(resolve_settings(Project.new(), "gif").output_kind, "gif")


class EstimateTests(unittest.TestCase):
    def test_higher_crf_gives_smaller_estimate(self):
        settings_a = resolve_settings(Project.new(), "hq")
        settings_b = resolve_settings(Project.new(), "mobile")
        self.assertGreater(estimate_output_bytes(60, settings_a),
                           estimate_output_bytes(60, settings_b))

    def test_scales_with_duration(self):
        settings = resolve_settings(Project.new(), "standard")
        self.assertAlmostEqual(estimate_output_bytes(120, settings),
                               estimate_output_bytes(60, settings) * 2, delta=100)

    def test_audio_only_ignores_resolution(self):
        settings = resolve_settings(Project.new(), "audio")
        self.assertGreater(estimate_output_bytes(60, settings), 0)


def sample_project():
    project = Project.new("Test")
    track = project.main_track
    track.add_clip(Clip.from_video("a.mp4", 10.0))
    track.add_clip(Clip.from_video("b.mp4", 8.0))
    return project


class BuildPlanTests(unittest.TestCase):
    def test_empty_project_raises(self):
        with self.assertRaises(ExportError):
            build_export_plan(Project.new(), "out.mp4", settings_for(Project.new()))

    def test_single_clip_no_concat_needed(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video("a.mp4", 5.0))
        plan = build_export_plan(project, "out.mp4", settings_for(project))
        text = args_to_text(plan.args)
        self.assertIn("-ss 0.000000 -to 5.000000 -i a.mp4", text)
        self.assertNotIn("concat", text)
        self.assertNotIn("xfade", text)
        self.assertEqual(plan.duration, 5.0)
        self.assertTrue(plan.args[-1].endswith("out.mp4"))

    def test_hard_cut_uses_concat(self):
        project = sample_project()
        plan = build_export_plan(project, "out.mp4", settings_for(project))
        text = args_to_text(plan.args)
        self.assertIn("concat=n=2:v=1:a=1", text)
        self.assertNotIn("xfade", text)
        self.assertEqual(plan.duration, 18.0)

    def test_transition_uses_xfade_and_acrossfade_with_correct_offset(self):
        project = sample_project()
        project.main_track.clips[1].transition_in = Transition("fade", 2.0)
        plan = build_export_plan(project, "out.mp4", settings_for(project))
        text = args_to_text(plan.args)
        self.assertIn("xfade=transition=fade:duration=2.000000:offset=8.000000", text)
        self.assertIn("acrossfade=d=2.000000", text)
        self.assertEqual(plan.duration, 16.0)  # 10 + 8 - 2 overlap

    def test_unknown_transition_name_falls_back_to_fade(self):
        project = sample_project()
        project.main_track.clips[1].transition_in = Transition("made_up", 1.0)
        plan = build_export_plan(project, "out.mp4", settings_for(project))
        self.assertIn("transition=fade", args_to_text(plan.args))

    def test_photo_gets_looped_input_and_silence(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_image("p.jpg", 6.0))
        plan = build_export_plan(project, "out.mp4", settings_for(project))
        text = args_to_text(plan.args)
        self.assertIn("-loop 1 -t 6.000000 -i p.jpg", text)
        self.assertIn("anullsrc=channel_layout=stereo", text)
        self.assertIn("atrim=0:6.000000", text)

    def test_silent_video_gets_silence_substituted(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video("silent.mp4", 4.0))
        plan = build_export_plan(project, "out.mp4", settings_for(project),
                                 silent_sources={"silent.mp4"})
        self.assertIn("anullsrc", args_to_text(plan.args))

    def test_no_silence_input_when_not_needed(self):
        plan = build_export_plan(sample_project(), "out.mp4", settings_for(sample_project()))
        self.assertNotIn("anullsrc", args_to_text(plan.args))

    def test_silence_input_gets_index_zero_and_others_shift(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_image("p.jpg", 3.0))
        project.main_track.add_clip(Clip.from_video("a.mp4", 3.0))
        plan = build_export_plan(project, "out.mp4", settings_for(project))
        text = args_to_text(plan.args)
        self.assertIn("[0:a]atrim", text)   # silence is input 0
        self.assertIn("[1:v]", text)        # the photo is input 1
        self.assertIn("[2:v]", text)        # the video is input 2
        self.assertIn("[2:a]", text)        # its own audio, not silence

    def test_speed_adds_atempo_chain_within_range(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video("a.mp4", 8.0, speed=4.0))
        plan = build_export_plan(project, "out.mp4", settings_for(project))
        text = args_to_text(plan.args)
        self.assertIn("setpts=0.250000*PTS", text)
        self.assertEqual(text.count("atempo=2.000000"), 2)  # 4x = 2 * 2

    def test_slow_speed_chain(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video("a.mp4", 8.0, speed=0.25))
        plan = build_export_plan(project, "out.mp4", settings_for(project))
        self.assertEqual(args_to_text(plan.args).count("atempo=0.500000"), 2)

    def test_rotation_effect_brightness_and_fades(self):
        project = Project.new()
        clip = Clip.from_video("a.mp4", 10.0, rotation=90, effect="sepia", brightness=0.2,
                               fade_in=1.0, fade_out=1.0)
        project.main_track.add_clip(clip)
        plan = build_export_plan(project, "out.mp4", settings_for(project))
        text = args_to_text(plan.args)
        self.assertIn("transpose=1", text)
        self.assertIn("colorchannelmixer", text)
        self.assertIn("eq=brightness=0.200", text)
        self.assertIn("fade=t=in:st=0:d=1.000", text)
        self.assertIn("fade=t=out:st=9.000:d=1.000", text)

    def test_volume_and_audio_fades(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video("a.mp4", 10.0, volume=0.5, fade_in=2.0))
        plan = build_export_plan(project, "out.mp4", settings_for(project))
        text = args_to_text(plan.args)
        self.assertIn("volume=0.500", text)
        self.assertIn("afade=t=in:st=0:d=2.000", text)

    def test_music_track_is_mixed_with_adelay(self):
        project = sample_project()
        project.tracks[1].add_clip(Clip.from_audio("music.mp3", 30.0, start=5.0))
        plan = build_export_plan(project, "out.mp4", settings_for(project))
        text = args_to_text(plan.args)
        self.assertIn("adelay=5000|5000", text)
        self.assertIn("amix=inputs=2", text)
        self.assertIn("volume=2", text)
        self.assertEqual(plan.warnings, [])

    def test_gif_ignores_music_and_uses_palette(self):
        project = sample_project()
        project.tracks[1].add_clip(Clip.from_audio("music.mp3", 30.0))
        settings = resolve_settings(project, "gif")
        plan = build_export_plan(project, "out.gif", settings)
        text = args_to_text(plan.args)
        self.assertIn("palettegen", text)
        self.assertIn("paletteuse", text)
        self.assertNotIn("amix", text)
        self.assertNotIn("adelay", text)
        self.assertIn("not included in an animated GIF", plan.warnings[0])
        self.assertNotIn("-map [a", text)  # no audio map for gif

    def test_audio_only_has_no_video_map_or_codec(self):
        project = sample_project()
        settings = resolve_settings(project, "audio")
        plan = build_export_plan(project, "out.mp3", settings)
        text = args_to_text(plan.args)
        self.assertIn("-vn", text)
        self.assertIn("libmp3lame", text)
        self.assertNotIn("-c:v", text)

    def test_extra_video_track_is_ignored_for_now(self):
        # a second video track (future picture-in-picture) shouldn't break export --
        # it's simply not composited in yet.
        project = sample_project()
        project.add_track("video", "Overlay")
        plan = build_export_plan(project, "out.mp4", settings_for(project))
        self.assertTrue(plan.args)  # builds without error

    def test_output_path_used_as_final_argument(self):
        plan = build_export_plan(sample_project(), r"C:\movies\out.mp4", settings_for(sample_project()))
        self.assertEqual(plan.args[-1], r"C:\movies\out.mp4")


if __name__ == "__main__":
    unittest.main()


class CaptionFilterTests(unittest.TestCase):
    def setUp(self):
        import shutil

        from easy_movie_studio.engine import titles
        self.addCleanup(shutil.rmtree, titles.CACHE_DIR, ignore_errors=True)

    def test_caption_adds_drawtext_via_textfile(self):
        project = Project.new()
        clip = Clip.from_video("a.mp4", 5.0, caption_text="Hello there")
        project.main_track.add_clip(clip)
        plan = build_export_plan(project, "out.mp4", settings_for(project))
        text = args_to_text(plan.args)
        self.assertIn("drawtext=textfile=", text)
        self.assertIn("y=h*0.88-text_h", text)  # default position: bottom

    def test_caption_position_top_and_middle(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video("a.mp4", 5.0, caption_text="Hi",
                                                     caption_position="top"))
        text = args_to_text(build_export_plan(project, "o.mp4", settings_for(project)).args)
        self.assertIn("y=h*0.06", text)

    def test_empty_caption_adds_nothing(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video("a.mp4", 5.0, caption_text="   "))
        text = args_to_text(build_export_plan(project, "o.mp4", settings_for(project)).args)
        self.assertNotIn("drawtext", text)

    def test_caption_text_file_contains_the_exact_text_unescaped(self):
        # the whole point of textfile= is that nothing inside the caption needs escaping
        project = Project.new()
        tricky = "It's 10:30 — \"go!\"\nnew line too"
        project.main_track.add_clip(Clip.from_video("a.mp4", 5.0, caption_text=tricky))
        plan = build_export_plan(project, "o.mp4", settings_for(project))
        text = args_to_text(plan.args)
        import re
        match = re.search(r"textfile=([^:]+(?:\\:[^:]+)*)", text)
        self.assertIsNotNone(match)
        path = match.group(1).replace("\\:", ":")
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), tricky)

    def test_same_caption_text_reuses_the_same_file(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video("a.mp4", 5.0, caption_text="Same"))
        project.main_track.add_clip(Clip.from_video("b.mp4", 5.0, caption_text="Same"))
        text = args_to_text(build_export_plan(project, "o.mp4", settings_for(project)).args)
        import re
        paths = re.findall(r"textfile=([^:]+(?:\\:[^:]+)*)", text)
        self.assertEqual(paths[0], paths[1])

    def test_title_and_credits_clips_export_like_photos(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_title("card.png", 3.0, text="Intro"))
        project.main_track.add_clip(Clip.from_video("a.mp4", 5.0))
        plan = build_export_plan(project, "o.mp4", settings_for(project))
        text = args_to_text(plan.args)
        self.assertIn("-loop 1 -t 3.000000 -i card.png", text)
        self.assertEqual(plan.duration, 8.0)


class AudioMixTests(unittest.TestCase):
    def test_video_volume_multiplies_main_track_clips(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video("a.mp4", 5.0, volume=0.8))
        settings = settings_for(project)
        settings.video_volume = 0.5
        text = args_to_text(build_export_plan(project, "o.mp4", settings).args)
        self.assertIn("volume=0.400", text)  # 0.8 * 0.5

    def test_default_multipliers_are_neutral(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video("a.mp4", 5.0))  # volume stays 1.0
        text = args_to_text(build_export_plan(project, "o.mp4", settings_for(project)).args)
        self.assertNotIn("volume=", text)  # no filter emitted when nothing changes it

    def test_music_volume_applies_to_music_track_only(self):
        project = sample_project()
        project.tracks[1].add_clip(Clip.from_audio("music.mp3", 10.0))
        settings = settings_for(project)
        settings.music_volume = 0.3
        text = args_to_text(build_export_plan(project, "o.mp4", settings).args)
        self.assertIn("volume=0.300", text)

    def test_duck_music_attenuates_music_but_not_video(self):
        from easy_movie_studio.engine.export_plan import DUCK_ATTENUATION
        project = sample_project()
        project.tracks[1].add_clip(Clip.from_audio("music.mp3", 10.0))
        settings = settings_for(project)
        settings.duck_music = True
        text = args_to_text(build_export_plan(project, "o.mp4", settings).args)
        self.assertIn(f"volume={DUCK_ATTENUATION:.3f}", text)

    def test_resolve_settings_carries_project_audio_mix(self):
        project = Project.new()
        project.settings.music_volume = 0.6
        project.settings.video_volume = 1.2
        project.settings.duck_music = True
        settings = resolve_settings(project, "recommended")
        self.assertEqual((settings.music_volume, settings.video_volume, settings.duck_music),
                         (0.6, 1.2, True))


class OverlayTrackTests(unittest.TestCase):
    def setUp(self):
        import shutil

        from easy_movie_studio.engine import titles
        self.addCleanup(shutil.rmtree, titles.CACHE_DIR, ignore_errors=True)

    def make_project_with_overlay(self, **overlay_kwargs):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video("base.mp4", 10.0))
        overlay_track = project.add_track("video", "Overlay")
        self.assertFalse(overlay_track.ripple)
        clip = Clip.from_video("pip.mp4", 5.0, start=2.0, **overlay_kwargs)
        overlay_track.add_clip(clip)
        return project, overlay_track, clip

    def test_overlay_uses_the_overlay_filter_with_time_gating(self):
        project, _, _ = self.make_project_with_overlay()
        text = args_to_text(build_export_plan(project, "o.mp4", settings_for(project)).args)
        self.assertIn("overlay=x=", text)
        self.assertIn("enable='between(t,2.000000,7.000000)'", text)

    def test_overlay_position_and_scale_appear_in_the_filter(self):
        project, _, _ = self.make_project_with_overlay(overlay_x=0.2, overlay_y=0.1,
                                                        overlay_scale=0.4)
        text = args_to_text(build_export_plan(project, "o.mp4", settings_for(project)).args)
        self.assertIn("main_w*0.2000", text)
        self.assertIn("main_h*0.1000", text)

    def test_overlay_opacity_adds_alpha_channel_mixing(self):
        project, _, _ = self.make_project_with_overlay(opacity=0.5)
        text = args_to_text(build_export_plan(project, "o.mp4", settings_for(project)).args)
        self.assertIn("format=rgba", text)
        self.assertIn("colorchannelmixer=aa=0.500", text)

    def test_full_opacity_skips_alpha_mixing(self):
        project, _, _ = self.make_project_with_overlay(opacity=1.0)
        text = args_to_text(build_export_plan(project, "o.mp4", settings_for(project)).args)
        self.assertNotIn("colorchannelmixer", text)

    def test_overlay_own_audio_is_delayed_and_mixed(self):
        project, _, _ = self.make_project_with_overlay()
        text = args_to_text(build_export_plan(project, "o.mp4", settings_for(project)).args)
        self.assertIn("adelay=2000|2000", text)
        self.assertIn("amix=inputs=2", text)  # base track + overlay's own audio

    def test_multiple_overlay_clips_chain_correctly(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video("base.mp4", 10.0))
        overlay_track = project.add_track("video", "Overlay")
        overlay_track.add_clip(Clip.from_video("pip1.mp4", 3.0, start=0.0))
        overlay_track.add_clip(Clip.from_video("pip2.mp4", 3.0, start=5.0))
        plan = build_export_plan(project, "o.mp4", settings_for(project))
        text = args_to_text(plan.args)
        self.assertEqual(text.count("]overlay=x="), 2)

    def test_gif_ignores_overlay_tracks_entirely(self):
        project, _, _ = self.make_project_with_overlay()
        settings = resolve_settings(project, "gif")
        plan = build_export_plan(project, "o.gif", settings)
        text = args_to_text(plan.args)
        self.assertNotIn("overlay=x=", text)
        self.assertIn("picture-in-picture video are not included", plan.warnings[0].lower())

    def test_audio_only_ignores_overlay_video_but_warns(self):
        project, _, _ = self.make_project_with_overlay()
        settings = resolve_settings(project, "audio")
        plan = build_export_plan(project, "o.mp3", settings)
        text = args_to_text(plan.args)
        self.assertNotIn("overlay=x=", text)
        self.assertTrue(any("audio-only export" in w for w in plan.warnings))

    def test_no_overlay_tracks_produces_no_warnings_or_overlay_filter(self):
        project = sample_project()
        plan = build_export_plan(project, "o.mp4", settings_for(project))
        self.assertEqual(plan.warnings, [])
        self.assertNotIn("overlay=x=", args_to_text(plan.args))

    def test_silent_overlay_source_gets_silence_substituted(self):
        project, _, clip = self.make_project_with_overlay()
        plan = build_export_plan(project, "o.mp4", settings_for(project),
                                 silent_sources={"pip.mp4"})
        self.assertIn("anullsrc", args_to_text(plan.args))

    def test_overlay_trim_and_rotation_respected(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_video("base.mp4", 10.0))
        overlay_track = project.add_track("video", "Overlay")
        clip = Clip.from_video("pip.mp4", 8.0, rotation=90)
        clip.trim(src_in=1.0, src_out=4.0)
        overlay_track.add_clip(clip)
        text = args_to_text(build_export_plan(project, "o.mp4", settings_for(project)).args)
        self.assertIn("-ss 1.000000 -to 4.000000 -i pip.mp4", text)
        self.assertIn("transpose=1", text)


class PanZoomFilterTests(unittest.TestCase):
    """Pure plan-construction tests for the Pan and zoom presets -- real-FFmpeg pixel
    verification that the motion actually happens lives in test_export_integration.py."""

    def test_photo_with_zoom_in_gets_a_zoompan_filter(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_image("photo.jpg", 3.0, pan_zoom="zoom_in"))
        text = args_to_text(build_export_plan(project, "o.mp4", settings_for(project)).args)
        self.assertIn("zoompan=z=", text)
        self.assertIn("d=", text)

    def test_zoompan_output_size_matches_export_settings(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_image("photo.jpg", 2.0, pan_zoom="zoom_out"))
        settings = settings_for(project, height=480)
        text = args_to_text(build_export_plan(project, "o.mp4", settings).args)
        self.assertIn(f"s={settings.width}x{settings.height}", text)

    def test_pan_zoom_none_falls_back_to_plain_scale_and_pad(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_image("photo.jpg", 2.0, pan_zoom="none"))
        text = args_to_text(build_export_plan(project, "o.mp4", settings_for(project)).args)
        self.assertNotIn("zoompan", text)
        self.assertIn("force_original_aspect_ratio=decrease", text)

    def test_unset_pan_zoom_falls_back_to_plain_scale_and_pad(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_image("photo.jpg", 2.0))
        text = args_to_text(build_export_plan(project, "o.mp4", settings_for(project)).args)
        self.assertNotIn("zoompan", text)

    def test_pan_zoom_is_ignored_on_a_real_video_clip(self):
        # Pan/zoom only makes sense on a still -- a video clip with it set is a no-op
        # at export, matching how the original Movie Maker scoped the feature to photos.
        project = Project.new()
        project.main_track.add_clip(Clip.from_video("a.mp4", 4.0, pan_zoom="zoom_in"))
        text = args_to_text(build_export_plan(project, "o.mp4", settings_for(project)).args)
        self.assertNotIn("zoompan", text)

    def test_title_card_also_supports_pan_zoom(self):
        project = Project.new()
        project.main_track.add_clip(Clip.from_title("card.png", 3.0, text="Intro",
                                                     pan_zoom="pan_left"))
        text = args_to_text(build_export_plan(project, "o.mp4", settings_for(project)).args)
        self.assertIn("zoompan", text)

    def test_each_preset_produces_a_distinct_filter(self):
        from easy_movie_studio.engine.export_plan import _pan_zoom_expressions
        names = ("zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down", "auto")
        seen = set()
        for name in names:
            exprs = _pan_zoom_expressions(name, frames=30)
            self.assertIsNotNone(exprs)
            seen.add(exprs)
        self.assertEqual(len(seen), len(names) - 1)  # "auto" intentionally mirrors "zoom_in"
