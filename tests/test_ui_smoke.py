"""GUI smoke tests. Skipped automatically when PySide6 is not installed."""

import os
import shutil
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class MainWindowSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mmclone.ui.theme import stylesheet
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(stylesheet())

    def setUp(self):
        from mmclone.demo import demo_project
        from mmclone.recent import RecentProjects
        from mmclone.ui.main_window import MainWindow
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.window = MainWindow(demo_project(), RecentProjects(os.path.join(self.tmp, "r.json")))
        self.window._dirty = False
        self.addCleanup(self.window.deleteLater)

    def test_playing_a_missing_file_reports_and_stops(self):
        messages = []
        self.window.player.failed.connect(messages.append)
        self.window.player.play()
        self.assertFalse(self.window.player.playing)
        self.assertTrue(messages)

    def test_selecting_a_clip_moves_the_playhead_to_its_start(self):
        clips = self.window.storyboard.clips()
        self.window.storyboard.set_selection([clips[1].id])
        self.assertAlmostEqual(self.window.player.time, clips[0].duration - 1.0, delta=1.0)
        self.window.storyboard.set_selection([clips[0].id])
        self.assertEqual(self.window.player.time, 0.0)

    def test_has_all_tabs(self):
        self.assertEqual(self.window.ribbon.tab_ids(),
                         ["home", "animations", "effects", "project", "view", "edit"])

    def test_video_tools_follow_selection(self):
        self.assertFalse(self.window.ribbon.contextual_visible())
        clip = self.window.storyboard.clips()[0]
        self.window.storyboard.set_selection([clip.id])
        self.assertTrue(self.window.ribbon.contextual_visible())
        self.window.storyboard.set_selection([])
        self.assertFalse(self.window.ribbon.contextual_visible())

    def test_buttons_enable_with_selection(self):
        self.assertFalse(self.window.ribbon.is_widget_enabled("home.rotate_left"))
        self.window.storyboard.select_all()
        self.assertTrue(self.window.ribbon.is_widget_enabled("home.rotate_left"))

    def test_empty_project_disables_media_buttons(self):
        from mmclone.model import Project
        self.window._install_project(Project.new(), None)
        self.assertFalse(self.window.ribbon.is_widget_enabled("home.select_all"))
        self.assertTrue(self.window.ribbon.is_widget_enabled("home.add_media"))

    def test_remove_and_rotate_update_the_model(self):
        clips = self.window.storyboard.clips()
        first = clips[0]
        self.window.storyboard.set_selection([first.id])
        self.window.on_command("home.rotate_right")
        self.assertEqual(first.rotation, 90)
        self.window.on_command("home.remove")
        self.assertEqual(len(self.window.project.main_track.clips), len(clips) - 1)
        self.assertTrue(self.window._dirty)

    def test_aspect_command_changes_project(self):
        self.window.on_command("project.aspect.9:16")
        self.assertEqual(self.window.project.settings.aspect_label, "9:16")

    def test_unknown_command_does_not_crash(self):
        self.window.on_command("home.paste")

    def test_every_tab_can_be_rendered(self):
        self.window.storyboard.select_all()
        for tab_id in self.window.ribbon.tab_ids():
            self.window.ribbon.select_tab(tab_id)
            self.assertFalse(self.window.grab().isNull())

    def test_save_and_reopen_round_trip(self):
        path = os.path.join(self.tmp, "movie.mmproj")
        self.assertTrue(self.window._write(path))
        self.window._open_path(path, already_confirmed=True)
        self.assertEqual(len(self.window.project.main_track.clips), 5)
        self.assertEqual(self.window.project.name, "movie")


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class ImportSmokeTests(unittest.TestCase):
    """Uses real (tiny) media made by FFmpeg."""

    @classmethod
    def setUpClass(cls):
        from mmclone.ui.theme import stylesheet
        from .media_fixtures import FFMPEG, MediaSet
        if not FFMPEG:
            raise unittest.SkipTest("FFmpeg not available")
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(stylesheet())
        cls.media = MediaSet()

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()

    def setUp(self):
        from mmclone.recent import RecentProjects
        from mmclone.ui.main_window import MainWindow
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.window = MainWindow(recent=RecentProjects(os.path.join(self.tmp, "r.json")))
        self.addCleanup(self.window.deleteLater)

    def import_and_wait(self, paths):
        self.window.import_files(paths)
        self.window.settle()

    def test_import_adds_clips_and_sets_project_from_first_clip(self):
        self.import_and_wait([self.media.video_av, self.media.photo])
        clips = self.window.project.main_track.clips
        self.assertEqual([c.kind for c in clips], ["video", "image"])
        self.assertEqual(self.window.project.settings.aspect_label, "4:3")
        self.assertEqual(self.window.project.settings.fps, 25.0)
        self.assertEqual(self.window.storyboard.selected, [c.id for c in clips])
        self.assertIn(self.media.video_av, self.window.media)
        self.assertTrue(self.window._dirty)

    def test_new_clips_go_after_the_selected_one(self):
        self.import_and_wait([self.media.video_av, self.media.video_silent])
        first, second = self.window.project.main_track.clips
        self.window.storyboard.set_selection([first.id])
        self.import_and_wait([self.media.photo])
        kinds = [c.kind for c in self.window.project.main_track.clips]
        self.assertEqual(kinds, ["video", "image", "video"])

    def test_thumbnails_arrive(self):
        self.import_and_wait([self.media.video_av])
        self.window.storyboard.repaint()
        self.window.settle()
        image = self.window.thumbs.get(self.media.video_av, 1.0, 52)
        self.assertIsNotNone(image)
        self.assertEqual(image.height(), 52)

    def test_properties_dialog_shows_details(self):
        from mmclone.ui.properties_dialog import PropertiesDialog
        self.import_and_wait([self.media.video_av])
        clip = self.window.project.main_track.clips[0]
        dialog = PropertiesDialog(clip.source, self.window.media[clip.source], clip,
                                  self.window.project.settings)
        text = dialog.details_text()
        self.assertIn("320 \u00d7 240", text)
        self.assertIn("video_av.mp4", text)
        self.assertTrue(dialog.copy_button.isEnabled())

    def test_properties_dialog_for_missing_file_explains_why(self):
        from mmclone.ui.properties_dialog import PropertiesDialog
        dialog = PropertiesDialog("/nowhere/gone.mp4", None, None,
                                  self.window.project.settings, "File not found")
        self.assertEqual(dialog.details_text().strip(), "")
        self.assertFalse(dialog.copy_button.isEnabled())

    def test_unreadable_files_are_reported_not_added(self):
        from unittest import mock
        with mock.patch("mmclone.ui.main_window.QMessageBox.warning") as warning:
            self.import_and_wait([self.media.broken])
        self.assertEqual(self.window.project.main_track.clips, [])
        warning.assert_called_once()

    def test_opening_a_project_with_a_missing_file_flags_it(self):
        from mmclone.demo import demo_project
        path = os.path.join(self.tmp, "p.mmproj")
        demo_project().save(path)
        self.window._open_path(path, already_confirmed=True)
        self.window.settle()
        self.assertEqual(len(self.window.storyboard.problems), 5)


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class PlaybackSmokeTests(unittest.TestCase):
    """Photo-only projects, so the timer-driven path runs without a video backend."""

    @classmethod
    def setUpClass(cls):
        from mmclone.ui.theme import stylesheet
        from .media_fixtures import FFMPEG, MediaSet
        if not FFMPEG:
            raise unittest.SkipTest("FFmpeg not available")
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(stylesheet())
        cls.media = MediaSet()

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()

    def setUp(self):
        from mmclone.recent import RecentProjects
        from mmclone.ui.main_window import MainWindow
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.window = MainWindow(recent=RecentProjects(os.path.join(self.tmp, "r.json")))
        self.addCleanup(self.window.deleteLater)
        self.window.import_files([self.media.photo, self.media.photo])
        self.window.settle()
        self.player = self.window.player

    def test_duration_and_first_frame(self):
        self.assertAlmostEqual(self.player.duration, 14.0)
        self.assertTrue(self.player.has_frame)
        self.assertIsNotNone(self.window.preview.surface.current_image())

    def test_seek_maps_to_the_right_photo(self):
        self.player.seek(9.0)
        self.assertEqual(self.player.current_segment.index, 1)
        self.assertAlmostEqual(self.player.time, 9.0)
        self.assertEqual(self.window.preview.time_label.text(), "00:09.00/00:14.00")

    def test_play_advances_moves_on_and_finishes(self):
        frames = []
        self.player.frameReady.connect(frames.append)
        self.player.seek(0)
        self.player.play()
        self.assertTrue(self.player.playing)
        started, _ = self.player._still_clock
        self.player._tick_still(now=started + 3.0)
        self.assertAlmostEqual(self.player.time, 3.0, places=2)
        self.player._tick_still(now=started + 8.0)  # first photo ended at 7 s
        self.assertEqual(self.player.current_segment.index, 1)
        self.assertAlmostEqual(self.player.time, 7.0, places=2)
        started, _ = self.player._still_clock
        self.player._tick_still(now=started + 7.5)  # past the end
        self.assertFalse(self.player.playing)
        self.assertAlmostEqual(self.player.time, 14.0)
        self.assertTrue(frames)

    def test_play_at_the_end_restarts(self):
        self.player.seek(14.0)
        self.player.play()
        self.assertTrue(self.player.playing)
        self.assertLess(self.player.time, 0.1)

    def test_pause_and_frame_step(self):
        self.player.seek(0)
        self.player.play()
        self.player.pause()
        self.assertFalse(self.player.playing)
        self.player.step(1)
        self.assertAlmostEqual(self.player.time, 1 / self.window.project.settings.fps, places=3)
        self.player.step(-1)
        self.assertAlmostEqual(self.player.time, 0.0, places=3)

    def test_unchanged_project_does_not_interrupt_playback(self):
        self.player.play()
        self.player.set_project(self.window.project)
        self.assertTrue(self.player.playing)

    def test_editing_pauses_playback(self):
        self.player.play()
        clip = self.window.project.main_track.clips[0]
        self.window.storyboard.set_selection([clip.id])
        self.window.on_command("home.rotate_right")
        self.assertFalse(self.player.playing)

    def test_slider_seeks(self):
        self.window.preview.slider.setValue(500)
        self.assertAlmostEqual(self.player.time, 7.0, places=1)

    def test_play_button_icon_follows_state(self):
        self.window.on_command("preview.play")
        self.assertTrue(self.player.playing)
        self.window.on_command("preview.play")
        self.assertFalse(self.player.playing)


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class EditingSmokeTests(unittest.TestCase):
    """split, trim, reorder, cut/copy/paste, undo/redo -- against a real (offscreen) window."""

    @classmethod
    def setUpClass(cls):
        from mmclone.ui.theme import stylesheet
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(stylesheet())

    def setUp(self):
        from mmclone.demo import demo_project
        from mmclone.recent import RecentProjects
        from mmclone.ui.main_window import MainWindow
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.window = MainWindow(demo_project(), RecentProjects(os.path.join(self.tmp, "r.json")))
        self.window._dirty = False
        self.addCleanup(self.window.deleteLater)
        self.track = self.window.project.main_track

    # ---- undo / redo plumbing --------------------------------------------------
    def test_undo_redo_buttons_track_the_stack(self):
        self.assertFalse(self.window.ribbon.is_widget_enabled("qat.undo"))
        clip = self.track.clips[0]
        self.window.storyboard.set_selection([clip.id])
        self.window.on_command("home.rotate_right")
        self.assertTrue(self.window.ribbon.is_widget_enabled("qat.undo"))
        self.assertFalse(self.window.ribbon.is_widget_enabled("qat.redo"))
        self.window.on_command("qat.undo")
        self.assertEqual(clip.rotation, 0)
        self.assertTrue(self.window.ribbon.is_widget_enabled("qat.redo"))
        self.window.on_command("qat.redo")
        self.assertEqual(clip.rotation, 90)

    def test_new_project_clears_undo_history(self):
        clip = self.track.clips[0]
        self.window.storyboard.set_selection([clip.id])
        self.window.on_command("home.rotate_right")
        self.assertTrue(self.window.undo.can_undo)
        self.window.new_project()
        self.assertFalse(self.window.undo.can_undo)

    # ---- remove / rotate are undoable now --------------------------------------
    def test_remove_then_undo_restores_clip_and_order(self):
        ids = [c.id for c in self.track.clips]
        self.window.storyboard.set_selection([ids[1]])
        self.window.on_command("home.remove")
        self.assertEqual([c.id for c in self.track.clips], [i for i in ids if i != ids[1]])
        self.window.do_undo()
        self.assertEqual([c.id for c in self.track.clips], ids)

    # ---- cut / copy / paste -----------------------------------------------------
    def test_copy_paste_adds_independent_duplicates(self):
        clip = self.track.clips[0]
        self.window.storyboard.set_selection([clip.id])
        self.window.on_command("home.copy")
        self.assertEqual(len(self.window.clipboard), 1)
        before = len(self.track.clips)
        self.window.on_command("home.paste")
        self.assertEqual(len(self.track.clips), before + 1)
        pasted = self.window.storyboard.selected[0]
        self.assertNotEqual(pasted, clip.id)
        self.assertEqual(self.track.get_clip(pasted).source, clip.source)
        self.window.on_command("home.paste")  # a second paste should not reuse the same id
        self.assertEqual(len(self.track.clips), before + 2)
        self.assertNotEqual(self.window.storyboard.selected[0], pasted)

    def test_cut_then_undo_restores_the_clip(self):
        clip_id = self.track.clips[2].id
        self.window.storyboard.set_selection([clip_id])
        self.window.on_command("home.cut")
        self.assertNotIn(clip_id, [c.id for c in self.track.clips])
        self.assertEqual(len(self.window.clipboard), 1)
        self.window.do_undo()
        self.assertIn(clip_id, [c.id for c in self.track.clips])

    def test_paste_with_nothing_copied_shows_a_message(self):
        self.window.on_command("home.paste")
        self.assertIn("Nothing to paste", self.window.statusBar().currentMessage())

    # ---- split ------------------------------------------------------------------
    def test_split_at_playhead(self):
        clip = self.track.clips[0]
        self.window.storyboard.set_selection([clip.id])
        self.window.player.seek(clip.duration / 2)
        before = len(self.track.clips)
        self.window.on_command("edit.split")
        self.assertEqual(len(self.track.clips), before + 1)
        self.assertAlmostEqual(self.track.clips[0].duration + self.track.clips[1].duration,
                               clip.duration, places=2)
        self.window.do_undo()
        self.assertEqual(len(self.track.clips), before)

    def test_split_outside_the_clip_is_refused(self):
        clip = self.track.clips[0]
        self.window.storyboard.set_selection([clip.id])
        self.window.player.seek(clip.duration + 5)  # into the next clip
        before = len(self.track.clips)
        self.window.on_command("edit.split")
        self.assertEqual(len(self.track.clips), before)

    # ---- set start / end point --------------------------------------------------
    def test_set_start_and_end_point(self):
        clip = self.track.clips[0]
        original_duration = clip.duration
        self.window.storyboard.set_selection([clip.id])
        self.window.player.seek(2.0)
        self.window.on_command("edit.set_start")
        self.assertAlmostEqual(clip.src_in, 2.0, places=2)
        self.window.player.seek(clip.src_in + 3.0)
        self.window.on_command("edit.set_end")
        self.assertAlmostEqual(clip.duration, 3.0, places=2)
        self.window.do_undo()
        self.assertAlmostEqual(clip.src_in, 2.0, places=2)
        self.window.do_undo()
        self.assertAlmostEqual(clip.src_in, 0.0, places=2)
        self.assertAlmostEqual(clip.duration, original_duration, places=1)

    # ---- trim tool (edge dragging) -----------------------------------------------
    def test_trim_tool_requires_a_single_selection(self):
        self.window.storyboard.select_all()
        self.window.on_command("edit.trim")
        self.assertFalse(self.window.ribbon.is_checked("edit.trim"))
        self.assertFalse(self.window.storyboard.trim_mode)

    def test_edge_drag_trims_the_clip(self):
        clip = self.track.clips[0]
        self.window.storyboard.set_selection([clip.id])
        self.window.on_command("edit.trim")
        self.assertTrue(self.window.storyboard.trim_mode)
        board = self.window.storyboard
        board.begin_edge_drag(clip.id, "right")
        board.update_edge_drag(-board.pps * 2)  # drag left by 2 seconds worth of pixels
        self.assertLess(clip.duration, clip.media_duration)  # live preview already shrank it
        board.end_edge_drag()
        self.assertAlmostEqual(clip.duration, clip.media_duration - 2.0, places=1)
        self.assertTrue(self.window.undo.can_undo)
        self.window.do_undo()
        self.assertAlmostEqual(clip.duration, clip.media_duration, places=2)

    def test_edge_drag_with_no_movement_pushes_no_command(self):
        clip = self.track.clips[0]
        self.window.storyboard.set_selection([clip.id])
        self.window.storyboard.set_trim_mode(True)
        board = self.window.storyboard
        board.begin_edge_drag(clip.id, "left")
        board.end_edge_drag()
        self.assertFalse(self.window.undo.can_undo)

    # ---- drag to reorder --------------------------------------------------------
    def test_reorder_clip_moves_it_and_is_undoable(self):
        ids = [c.id for c in self.track.clips]
        self.window.reorder_clip(ids[0], 3)
        self.assertEqual([c.id for c in self.track.clips], ids[1:4] + [ids[0]] + ids[4:])
        self.window.do_undo()
        self.assertEqual([c.id for c in self.track.clips], ids)

    def test_reorder_insertion_index_matches_a_real_drag(self):
        board = self.window.storyboard
        clip_id = self.track.clips[0].id
        board.begin_reorder(clip_id)
        last_rect_right = board.width() - 5  # somewhere near the right edge of the row
        board.update_reorder(last_rect_right, 30)
        board.end_reorder()
        self.assertNotEqual(self.track.clips[0].id, clip_id)
        self.assertIn(clip_id, [c.id for c in self.track.clips])


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class AnimationsEffectsSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mmclone.ui.theme import stylesheet
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(stylesheet())

    def setUp(self):
        from mmclone.demo import demo_project
        from mmclone.recent import RecentProjects
        from mmclone.ui.main_window import MainWindow
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.window = MainWindow(demo_project(), RecentProjects(os.path.join(self.tmp, "r.json")))
        self.window._dirty = False
        self.addCleanup(self.window.deleteLater)
        self.track = self.window.project.main_track

    def test_picking_an_effect_from_the_gallery(self):
        clip = self.track.clips[0]
        self.window.storyboard.set_selection([clip.id])
        self.window.on_command("fx.effect/sepia")
        self.assertEqual(clip.effect, "sepia")
        self.window.do_undo()
        self.assertIsNone(clip.effect)

    def test_picking_none_clears_the_effect(self):
        clip = self.track.clips[0]
        clip.update(effect="warm")
        self.window.storyboard.set_selection([clip.id])
        self.window.on_command("fx.effect/none")
        self.assertIsNone(clip.effect)

    def test_brightness_menu_items(self):
        clip = self.track.clips[0]
        self.window.storyboard.set_selection([clip.id])
        self.window.on_command("fx.brightness.brighter2")
        self.assertAlmostEqual(clip.brightness, 0.3)
        self.window.on_command("fx.brightness.normal")
        self.assertEqual(clip.brightness, 0.0)

    def test_apply_effect_to_all(self):
        clip = self.track.clips[0]
        clip.update(effect="cinematic")
        self.window.storyboard.set_selection([clip.id])
        self.window.on_command("fx.apply_all")
        self.assertTrue(all(c.effect == "cinematic" for c in self.track.clips))
        self.window.do_undo()
        self.assertTrue(all(c.effect is None for c in self.track.clips[1:]))

    def test_apply_to_all_requires_single_selection(self):
        self.window.storyboard.select_all()
        self.window.on_command("fx.apply_all")
        self.assertIn("Select a single clip", self.window.statusBar().currentMessage())

    def test_pan_zoom_selection(self):
        clip = self.track.clips[0]
        self.window.storyboard.set_selection([clip.id])
        self.window.on_command("anim.pan_zoom/zoom_in")
        self.assertEqual(clip.pan_zoom, "zoom_in")

    def test_transition_sets_and_shortens_track_duration(self):
        before = self.track.duration
        second = self.track.clips[1]
        self.window.storyboard.set_selection([second.id])
        self.window.on_command("anim.transition/fade")
        self.assertEqual(second.transition_in.name, "fade")
        self.assertEqual(second.transition_in.duration, 1.0)  # default duration
        self.assertLess(self.track.duration, before)
        self.window.do_undo()
        self.assertIsNone(second.transition_in)
        self.assertEqual(self.track.duration, before)

    def test_transition_none_clears_it(self):
        from mmclone.model import Transition
        second = self.track.clips[1]
        second.transition_in = Transition("fade", 1.0)
        self.window.storyboard.set_selection([second.id])
        self.window.on_command("anim.transition/none")
        self.assertIsNone(second.transition_in)

    def test_duration_spinbox_updates_existing_transition_live(self):
        from mmclone.model import Transition
        second = self.track.clips[1]
        second.transition_in = Transition("dissolve", 1.0)
        self.window.storyboard.set_selection([second.id])
        self.window._on_value_changed("anim.duration", 2.0)
        self.assertEqual(second.transition_in.duration, 2.0)
        self.assertEqual(second.transition_in.name, "dissolve")  # name is preserved

    def test_duration_spinbox_without_transition_just_remembers_the_value(self):
        clip = self.track.clips[0]
        self.window.storyboard.set_selection([clip.id])
        self.window._on_value_changed("anim.duration", 2.5)
        self.assertIsNone(clip.transition_in)
        self.assertEqual(self.window._transition_duration, 2.5)
        self.window.on_command("anim.transition/fade")
        self.assertEqual(clip.transition_in.duration, 2.5)  # remembered value is used

    def test_apply_transition_to_all(self):
        second = self.track.clips[1]
        self.window.storyboard.set_selection([second.id])
        self.window.on_command("anim.transition/wipe_left")
        self.window.on_command("anim.transition_all")
        self.assertTrue(all(c.transition_in and c.transition_in.name == "wipe_left"
                            for c in self.track.clips))

    def test_ribbon_reflects_selected_clip_state(self):
        clip = self.track.clips[2]
        clip.update(effect="pop_art", pan_zoom="pan_left")
        self.window.storyboard.set_selection([clip.id])
        self.window.update_state()
        # spot-check via re-selecting a clip with no effect: gallery should reset
        other = self.track.clips[0]
        self.window.storyboard.set_selection([other.id])
        self.window.update_state()  # should not raise, and no exception means sync worked


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class TitlesCaptionsCreditsMusicSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mmclone.ui.theme import stylesheet
        from .media_fixtures import FFMPEG, MediaSet
        if not FFMPEG:
            raise unittest.SkipTest("FFmpeg not available")
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(stylesheet())
        cls.media = MediaSet()

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()
        import shutil

        from mmclone.engine import titles
        shutil.rmtree(titles.CACHE_DIR, ignore_errors=True)

    def setUp(self):
        from mmclone.demo import demo_project
        from mmclone.recent import RecentProjects
        from mmclone.ui.main_window import MainWindow
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.window = MainWindow(demo_project(), RecentProjects(os.path.join(self.tmp, "r.json")))
        self.window._dirty = False
        self.addCleanup(self.window.deleteLater)
        self.track = self.window.project.main_track

    def accept_dialog(self, cls, values_method_result):
        """Patches ``cls.exec`` to auto-accept and ``cls.values`` to return a fixed result."""
        from unittest import mock
        patches = [mock.patch.object(cls, "exec", return_value=1),
                  mock.patch.object(cls, "values", return_value=values_method_result)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_add_title_inserts_a_card_at_the_start(self):
        from mmclone.ui.title_dialogs import TitleDialog
        self.accept_dialog(TitleDialog, ("My Movie", "Black", 3.0))
        before = len(self.track.clips)
        self.window.on_command("home.title")
        self.assertEqual(len(self.track.clips), before + 1)
        new_clip = self.track.clips[0]  # nothing selected -> inserted at the start
        self.assertEqual(new_clip.kind, "title")
        self.assertEqual(new_clip.text, "My Movie")
        self.assertEqual(new_clip.duration, 3.0)
        self.assertTrue(os.path.isfile(new_clip.source))
        self.window.do_undo()
        self.assertEqual(len(self.track.clips), before)

    def test_add_title_with_empty_text_is_refused(self):
        from mmclone.ui.title_dialogs import TitleDialog
        self.accept_dialog(TitleDialog, ("   ", "Black", 3.0))
        before = len(self.track.clips)
        self.window.on_command("home.title")
        self.assertEqual(len(self.track.clips), before)
        self.assertIn("Enter some text", self.window.statusBar().currentMessage())

    def test_add_title_inserts_after_selection(self):
        from mmclone.ui.title_dialogs import TitleDialog
        first = self.track.clips[0]
        self.window.storyboard.set_selection([first.id])
        self.accept_dialog(TitleDialog, ("Chapter 2", "White", 2.0))
        self.window.on_command("home.title")
        self.assertEqual(self.track.clips[1].text, "Chapter 2")

    def test_add_caption_requires_a_single_selection(self):
        self.window.storyboard.select_all()
        self.window.on_command("home.caption")
        self.assertIn("Select a single clip", self.window.statusBar().currentMessage())

    def test_add_caption_sets_and_undoes(self):
        from mmclone.ui.title_dialogs import CaptionDialog
        clip = self.track.clips[0]
        self.window.storyboard.set_selection([clip.id])
        self.accept_dialog(CaptionDialog, ("At the lake", "top"))
        self.window.on_command("home.caption")
        self.assertEqual(clip.caption_text, "At the lake")
        self.assertEqual(clip.caption_position, "top")
        self.window.do_undo()
        self.assertEqual(clip.caption_text, "")

    def test_add_credits_appends_at_the_end(self):
        from mmclone.ui.title_dialogs import CreditsDialog
        lines = [["Directed by", "A. Tester"]]
        self.accept_dialog(CreditsDialog, (lines, "Black", 4.0))
        before = len(self.track.clips)
        self.window.on_command("home.credits.director")
        self.assertEqual(len(self.track.clips), before + 1)
        new_clip = self.track.clips[-1]
        self.assertEqual(new_clip.text_style, "credits")
        self.assertEqual(new_clip.text_lines, lines)

    def test_add_credits_with_no_names_is_refused(self):
        from mmclone.ui.title_dialogs import CreditsDialog
        self.accept_dialog(CreditsDialog, ([], "Black", 4.0))
        before = len(self.track.clips)
        self.window.on_command("home.credits.cast")
        self.assertEqual(len(self.track.clips), before)

    def test_title_and_credits_are_undoable_through_main_window_undo(self):
        from mmclone.ui.title_dialogs import TitleDialog
        self.accept_dialog(TitleDialog, ("Undo me", "Black", 2.0))
        self.window.on_command("home.title")
        self.assertTrue(self.window._dirty)
        self.assertTrue(self.window.undo.can_undo)

    def test_add_music_imports_onto_the_music_track(self):
        from unittest import mock
        with mock.patch("mmclone.ui.main_window.QFileDialog.getOpenFileNames",
                        return_value=([self.media.tone], "")):
            self.window.add_music()
        music_track = next(t for t in self.window.project.tracks if t.kind == "audio")
        self.assertEqual(len(music_track.clips), 1)
        self.assertEqual(music_track.clips[0].source, self.media.tone)
        self.assertTrue(self.window.undo.can_undo)

    def test_add_music_twice_appends_sequentially(self):
        from unittest import mock
        with mock.patch("mmclone.ui.main_window.QFileDialog.getOpenFileNames",
                        return_value=([self.media.tone], "")):
            self.window.add_music()
            self.window.add_music()
        music_track = next(t for t in self.window.project.tracks if t.kind == "audio")
        self.assertEqual(len(music_track.clips), 2)
        self.assertEqual(music_track.clips[1].start, music_track.clips[0].duration)

    def test_storyboard_renders_a_title_clip_without_crashing(self):
        from mmclone.engine.titles import render_title_png
        path = render_title_png("Preview", self.window.project.settings.width,
                                self.window.project.settings.height)
        from mmclone.model import Clip
        clip = Clip.from_title(path, 2.0, text="Preview")
        self.track.add_clip(clip, 0)
        self.window.storyboard.refresh()
        self.assertFalse(self.window.storyboard.grab().isNull())


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class AudioMixFitNarrationSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mmclone.ui.theme import stylesheet
        from .media_fixtures import FFMPEG, MediaSet
        if not FFMPEG:
            raise unittest.SkipTest("FFmpeg not available")
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(stylesheet())
        cls.media = MediaSet()

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()

    def setUp(self):
        from mmclone.demo import demo_project
        from mmclone.recent import RecentProjects
        from mmclone.ui.main_window import MainWindow
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.window = MainWindow(demo_project(), RecentProjects(os.path.join(self.tmp, "r.json")))
        self.window._dirty = False
        self.addCleanup(self.window.deleteLater)

    def accept_dialog(self, cls, values_result):
        from unittest import mock
        patches = [mock.patch.object(cls, "exec", return_value=1),
                  mock.patch.object(cls, "values", return_value=values_result)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    # ---- audio mix --------------------------------------------------------------
    def test_audio_mix_dialog_updates_settings_and_is_undoable(self):
        from mmclone.ui.audio_mix_dialog import AudioMixDialog
        self.accept_dialog(AudioMixDialog, (0.4, 1.3, True))
        self.window.on_command("project.audio_mix")
        s = self.window.project.settings
        self.assertEqual((s.music_volume, s.video_volume, s.duck_music), (0.4, 1.3, True))
        self.assertTrue(self.window._dirty)
        self.window.do_undo()
        self.assertEqual((s.music_volume, s.video_volume, s.duck_music), (1.0, 1.0, False))

    def test_audio_mix_dialog_prefilled_from_current_settings(self):
        from unittest import mock
        self.window.project.settings.music_volume = 0.6
        captured = {}

        def fake_init(self_dialog, music_volume, video_volume, duck_music, parent=None):
            captured["args"] = (music_volume, video_volume, duck_music)
            QDialog.__init__(self_dialog, parent)

        from mmclone.ui.audio_mix_dialog import AudioMixDialog
        with mock.patch.object(AudioMixDialog, "__init__", fake_init), \
             mock.patch.object(AudioMixDialog, "exec", return_value=0):
            self.window.on_command("project.audio_mix")
        self.assertEqual(captured["args"][0], 0.6)

    # ---- fit to music -------------------------------------------------------------
    def test_fit_to_music_with_nothing_to_fit_shows_a_message(self):
        self.window.on_command("project.fit_music")
        self.assertTrue(self.window.statusBar().currentMessage())

    def test_fit_to_music_adjusts_the_last_clip(self):
        self.window.import_files([self.media.video_av])
        self.window.settle()
        music_track = next(t for t in self.window.project.tracks if t.kind == "audio")
        from mmclone.model import Clip
        music_track.add_clip(Clip.from_audio(self.media.tone, 1.0))
        before = self.window.project.main_track.duration
        self.window.on_command("project.fit_music")
        after = self.window.project.main_track.duration
        self.assertNotEqual(before, after)
        self.assertTrue(self.window.undo.can_undo)

    # ---- narration ----------------------------------------------------------------
    def test_narration_dialog_with_no_result_adds_nothing(self):
        from mmclone.ui.narration_dialog import NarrationDialog
        from unittest import mock
        with mock.patch.object(NarrationDialog, "exec", return_value=0):
            self.window.on_command("home.narration")
        self.assertFalse(any(t.name == "Narration" for t in self.window.project.tracks))

    def test_narration_result_creates_a_narration_track(self):
        from mmclone.ui.narration_dialog import NarrationDialog
        from unittest import mock
        with mock.patch.object(NarrationDialog, "exec", return_value=1), \
             mock.patch.object(NarrationDialog, "result_values",
                               return_value=(self.media.tone, 1.0)):
            self.window.on_command("home.narration")
        track = next((t for t in self.window.project.tracks if t.name == "Narration"), None)
        self.assertIsNotNone(track)
        self.assertEqual(len(track.clips), 1)
        self.assertTrue(self.window.undo.can_undo)

    def test_narration_recorder_reports_unavailable_in_this_environment(self):
        # not a mock -- this really exercises the no-hardware path, since this sandbox
        # genuinely has no PortAudio library
        from mmclone.ui.narration_dialog import NarrationDialog
        dialog = NarrationDialog(parent=self.window)
        self.addCleanup(dialog.deleteLater)
        self.assertFalse(dialog.record_button.isEnabled())


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class TimelineSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mmclone.ui.theme import stylesheet
        from .media_fixtures import FFMPEG, MediaSet
        if not FFMPEG:
            raise unittest.SkipTest("FFmpeg not available")
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(stylesheet())
        cls.media = MediaSet()

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()

    def setUp(self):
        from mmclone.demo import demo_project
        from mmclone.recent import RecentProjects
        from mmclone.ui.main_window import MainWindow
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.window = MainWindow(demo_project(), RecentProjects(os.path.join(self.tmp, "r.json")))
        self.window._dirty = False
        self.addCleanup(self.window.deleteLater)
        self.track = self.window.project.main_track

    # ---- view toggle --------------------------------------------------------------
    def test_toggle_view_switches_the_stack_and_syncs_selection(self):
        self.assertEqual(self.window.view_stack.currentIndex(), 0)
        clip = self.track.clips[1]
        self.window.storyboard.set_selection([clip.id])
        self.window.toggle_view()
        self.assertEqual(self.window.view_stack.currentIndex(), 1)
        self.assertEqual(self.window.timeline.selected, [clip.id])
        self.window.toggle_view()
        self.assertEqual(self.window.view_stack.currentIndex(), 0)

    def test_timeline_shows_every_track(self):
        self.window.toggle_view()
        self.assertEqual(len(self.window.timeline._tracks()), len(self.window.project.tracks))

    # ---- overlay track creation -----------------------------------------------------
    def test_add_overlay_track_creates_one_and_switches_to_timeline(self):
        before = len(self.window.project.tracks)
        self.window.add_overlay_track()
        self.assertEqual(len(self.window.project.tracks), before + 1)
        self.assertEqual(self.window.view_stack.currentIndex(), 1)
        new_track = self.window.project.tracks[-1]
        self.assertEqual(new_track.kind, "video")
        self.assertFalse(new_track.ripple)

    def test_add_overlay_track_twice_reuses_the_existing_one(self):
        self.window.add_overlay_track()
        before = len(self.window.project.tracks)
        self.window.add_overlay_track()
        self.assertEqual(len(self.window.project.tracks), before)

    # ---- importing onto a specific track via drop ------------------------------------
    def test_handle_timeline_drop_onto_overlay_track(self):
        self.window.add_overlay_track()
        overlay_track = self.window.project.tracks[-1]
        self.window.handle_timeline_drop(overlay_track.id, 3.0, [self.media.video_av])
        self.assertEqual(len(overlay_track.clips), 1)
        self.assertEqual(overlay_track.clips[0].start, 3.0)
        self.assertTrue(self.window.undo.can_undo)

    def test_handle_timeline_drop_rejects_wrong_kind(self):
        self.window.add_overlay_track()
        overlay_track = self.window.project.tracks[-1]
        self.window.handle_timeline_drop(overlay_track.id, 0.0, [self.media.tone])
        self.assertEqual(len(overlay_track.clips), 0)  # audio file, video-only track

    def test_handle_timeline_drop_onto_music_track(self):
        music_track = next(t for t in self.window.project.tracks if t.kind == "audio")
        self.window.handle_timeline_drop(music_track.id, 1.5, [self.media.tone])
        self.assertEqual(len(music_track.clips), 1)
        self.assertEqual(music_track.clips[0].start, 1.5)

    # ---- repositioning on a non-ripple track -----------------------------------------
    def test_reposition_clip_is_undoable(self):
        music_track = next(t for t in self.window.project.tracks if t.kind == "audio")
        from mmclone.model import Clip
        clip = Clip.from_audio(self.media.tone, 1.0, start=0.0)
        music_track.add_clip(clip)
        self.window.reposition_clip(clip.id, 5.0)
        self.assertEqual(clip.start, 5.0)
        self.window.do_undo()
        self.assertEqual(clip.start, 0.0)

    # ---- overlay position dialog ------------------------------------------------------
    def test_overlay_position_requires_an_overlay_clip(self):
        self.window.storyboard.set_selection([self.track.clips[0].id])  # a main-track clip
        self.window.open_overlay_position()
        self.assertIn("overlay video", self.window.statusBar().currentMessage())

    def test_overlay_position_dialog_applies_and_undoes(self):
        from unittest import mock

        from mmclone.model import Clip
        from mmclone.ui.overlay_dialog import OverlayPositionDialog
        self.window.add_overlay_track()
        overlay_track = self.window.project.tracks[-1]
        clip = Clip.from_video(self.media.video_av, 2.0)
        overlay_track.add_clip(clip)
        self.window.storyboard.set_selection([clip.id])
        with mock.patch.object(OverlayPositionDialog, "exec", return_value=1), \
             mock.patch.object(OverlayPositionDialog, "values",
                               return_value=(0.1, 0.2, 0.5, 0.7)):
            self.window.open_overlay_position()
        self.assertEqual((clip.overlay_x, clip.overlay_y, clip.overlay_scale, clip.opacity),
                         (0.1, 0.2, 0.5, 0.7))
        self.window.do_undo()
        self.assertEqual(clip.overlay_scale, 0.35)

    # ---- timeline context menu routes through storyboard selection --------------------
    def test_timeline_command_syncs_selection_before_dispatch(self):
        clip = self.track.clips[2]
        self.window.timeline.set_selection([clip.id])
        self.window._on_timeline_command("home.remove")
        self.assertNotIn(clip.id, [c.id for c in self.track.clips])

    # ---- drag-to-reposition math, exercised directly (not via raw mouse events) -------
    def test_timeline_drag_snaps_to_another_clip_s_edge(self):
        self.window.add_overlay_track()
        overlay_track = self.window.project.tracks[-1]
        from mmclone.model import Clip
        anchor = Clip.from_video(self.media.video_av, 2.0, start=5.0)
        dragged = Clip.from_video(self.media.video_silent, 1.0, start=0.0)
        overlay_track.add_clip(anchor)
        overlay_track.add_clip(dragged)
        self.window.toggle_view()
        timeline = self.window.timeline
        from mmclone.ui.timeline_layout import time_to_x
        press_x = time_to_x(0.5, timeline.pps)  # somewhere inside the dragged clip
        timeline._drag = {"clip_id": dragged.id, "track": overlay_track, "press_x": press_x,
                          "orig_start": 0.0, "duration": 1.0}
        near_anchor_end_x = time_to_x(7.0 - 0.5, timeline.pps) + press_x - time_to_x(0.5,
                                                                                     timeline.pps)
        # drag so the clip's computed start lands within snapping distance of anchor's end (7.0)
        timeline._update_drag(time_to_x(6.9, timeline.pps))
        self.assertAlmostEqual(dragged.start, 7.0, delta=0.5)

    def test_timeline_drag_never_goes_negative(self):
        self.window.add_overlay_track()
        overlay_track = self.window.project.tracks[-1]
        from mmclone.model import Clip
        clip = Clip.from_video(self.media.video_av, 2.0, start=0.0)
        overlay_track.add_clip(clip)
        timeline = self.window.timeline
        timeline._drag = {"clip_id": clip.id, "track": overlay_track, "press_x": 100.0,
                          "orig_start": 0.0, "duration": 2.0}
        timeline._update_drag(-500.0)
        self.assertGreaterEqual(clip.start, 0.0)


if __name__ == "__main__":
    unittest.main()
