import unittest

from easy_movie_studio.commands import (AddClipsCommand, MoveClipCommand, RemoveClipsCommand,
                              RotateClipsCommand, SetAspectCommand, SplitClipCommand,
                              TrimClipCommand, UndoStack)
from easy_movie_studio.model import Clip, Project, Track


def track_with(*durations):
    track = Track(kind="video")
    for i, d in enumerate(durations):
        track.add_clip(Clip.from_video(f"v{i}.mp4", d))
    return track


class UndoStackTests(unittest.TestCase):
    class Increment:
        label = "increment"

        def __init__(self, box, amount=1):
            self.box, self.amount = box, amount

        def do(self):
            self.box[0] += self.amount

        def undo(self):
            self.box[0] -= self.amount

    def test_push_do_undo_redo(self):
        box = [0]
        stack = UndoStack()
        stack.push(self.Increment(box))
        stack.push(self.Increment(box, 5))
        self.assertEqual(box[0], 6)
        stack.undo()
        self.assertEqual(box[0], 1)
        stack.undo()
        self.assertEqual(box[0], 0)
        self.assertFalse(stack.can_undo)
        stack.redo()
        stack.redo()
        self.assertEqual(box[0], 6)
        self.assertFalse(stack.can_redo)

    def test_push_clears_redo(self):
        box = [0]
        stack = UndoStack()
        stack.push(self.Increment(box))
        stack.undo()
        stack.push(self.Increment(box, 9))
        self.assertFalse(stack.can_redo)
        self.assertEqual(box[0], 9)

    def test_undo_redo_on_empty_stack_is_a_no_op(self):
        stack = UndoStack()
        stack.undo()
        stack.redo()  # neither should raise

    def test_on_change_fires_for_push_undo_redo_and_clear(self):
        calls = []
        stack = UndoStack(on_change=lambda: calls.append(1))
        stack.push(self.Increment([0]))
        stack.undo()
        stack.redo()
        stack.clear()
        self.assertEqual(len(calls), 4)

    def test_labels(self):
        stack = UndoStack()
        self.assertIsNone(stack.undo_label)
        stack.push(self.Increment([0]))
        self.assertEqual(stack.undo_label, "increment")
        self.assertIsNone(stack.redo_label)
        stack.undo()
        self.assertEqual(stack.redo_label, "increment")

    def test_limit_drops_oldest(self):
        box = [0]
        stack = UndoStack(limit=3)
        for _ in range(5):
            stack.push(self.Increment(box))
        for _ in range(3):
            stack.undo()
        self.assertEqual(box[0], 2)  # only the 3 most recent could be undone
        self.assertFalse(stack.can_undo)


class AddRemoveCommandTests(unittest.TestCase):
    def test_add_then_undo(self):
        track = track_with(5)
        new_clips = [Clip.from_video("a.mp4", 3), Clip.from_video("b.mp4", 4)]
        command = AddClipsCommand(track, new_clips, index=1)
        command.do()
        self.assertEqual([c.source for c in track.clips], ["v0.mp4", "a.mp4", "b.mp4"])
        command.undo()
        self.assertEqual([c.source for c in track.clips], ["v0.mp4"])

    def test_remove_preserves_order_on_undo(self):
        track = track_with(1, 2, 3, 4)
        ids = [c.id for c in track.clips]
        command = RemoveClipsCommand(track, [ids[1], ids[3]])
        command.do()
        self.assertEqual([c.id for c in track.clips], [ids[0], ids[2]])
        command.undo()
        self.assertEqual([c.id for c in track.clips], ids)

    def test_remove_all_then_undo(self):
        track = track_with(1, 2, 3)
        ids = [c.id for c in track.clips]
        command = RemoveClipsCommand(track, ids)
        command.do()
        self.assertEqual(track.clips, [])
        command.undo()
        self.assertEqual([c.id for c in track.clips], ids)

    def test_stack_integration(self):
        track = track_with(5)
        stack = UndoStack()
        stack.push(AddClipsCommand(track, [Clip.from_video("a.mp4", 2)], index=1))
        self.assertEqual(len(track.clips), 2)
        stack.undo()
        self.assertEqual(len(track.clips), 1)
        stack.redo()
        self.assertEqual(len(track.clips), 2)


class MoveCommandTests(unittest.TestCase):
    def test_move_and_undo(self):
        track = track_with(1, 2, 3)
        ids = [c.id for c in track.clips]
        command = MoveClipCommand(track, ids[2], 0)
        command.do()
        self.assertEqual([c.id for c in track.clips], [ids[2], ids[0], ids[1]])
        command.undo()
        self.assertEqual([c.id for c in track.clips], ids)


class RotateCommandTests(unittest.TestCase):
    def test_rotate_multiple_and_undo(self):
        track = track_with(1, 2)
        ids = [c.id for c in track.clips]
        command = RotateClipsCommand(track, ids, 90)
        command.do()
        self.assertEqual([c.rotation for c in track.clips], [90, 90])
        command.undo()
        self.assertEqual([c.rotation for c in track.clips], [0, 0])

    def test_redo_via_stack(self):
        track = track_with(1)
        clip_id = track.clips[0].id
        stack = UndoStack()
        stack.push(RotateClipsCommand(track, [clip_id], 90))
        stack.undo()
        stack.redo()
        self.assertEqual(track.clips[0].rotation, 90)


class TrimCommandTests(unittest.TestCase):
    def test_trim_and_undo(self):
        track = track_with(10)
        clip_id = track.clips[0].id
        command = TrimClipCommand(track, clip_id, new_in=2.0, new_out=6.0)
        command.do()
        self.assertEqual((track.clips[0].src_in, track.clips[0].src_out), (2.0, 6.0))
        command.undo()
        self.assertEqual((track.clips[0].src_in, track.clips[0].src_out), (0.0, 10.0))


class SplitCommandTests(unittest.TestCase):
    def test_split_and_undo_removes_second_half(self):
        track = track_with(10)
        clip_id = track.clips[0].id
        command = SplitClipCommand(track, clip_id, at=4.0)
        command.do()
        self.assertEqual(len(track.clips), 2)
        self.assertIsNotNone(command.new_clip_id)
        self.assertEqual(track.clips[0].src_out, 4.0)
        command.undo()
        self.assertEqual(len(track.clips), 1)
        self.assertEqual(track.clips[0].src_out, 10.0)

    def test_split_redo_via_stack_produces_a_fresh_second_half(self):
        # redo re-runs do(), which re-splits and hands out a new id for the second
        # half each time -- that is expected, not a bug -- so only the shape is checked.
        track = track_with(10)
        clip_id = track.clips[0].id
        stack = UndoStack()
        command = SplitClipCommand(track, clip_id, at=4.0)
        stack.push(command)
        stack.undo()
        stack.redo()
        self.assertEqual(len(track.clips), 2)
        self.assertEqual(track.clips[0].id, clip_id)
        self.assertEqual(track.clips[0].src_out, 4.0)
        self.assertEqual(track.clips[1].id, command.new_clip_id)
        self.assertNotEqual(command.new_clip_id, clip_id)


class AspectCommandTests(unittest.TestCase):
    def test_change_and_undo(self):
        project = Project.new()
        command = SetAspectCommand(project, "9:16")
        command.do()
        self.assertEqual(project.settings.aspect_label, "9:16")
        command.undo()
        self.assertEqual(project.settings.aspect_label, "16:9")


class IntegrationTests(unittest.TestCase):
    def test_a_sequence_of_edits_fully_undoes_and_redoes(self):
        track = track_with(4, 6, 8)
        ids = [c.id for c in track.clips]
        stack = UndoStack()
        stack.push(RotateClipsCommand(track, [ids[0]], 90))
        stack.push(RemoveClipsCommand(track, [ids[1]]))
        stack.push(MoveClipCommand(track, ids[2], 0))
        stack.push(TrimClipCommand(track, ids[0], 1.0, 3.0))
        snapshot_after = [c.to_dict() for c in track.clips]

        for _ in range(4):
            stack.undo()
        self.assertEqual([c.id for c in track.clips], ids)
        self.assertEqual(track.clips[0].rotation, 0)
        self.assertEqual((track.clips[0].src_in, track.clips[0].src_out), (0.0, 4.0))

        for _ in range(4):
            stack.redo()
        self.assertEqual([c.to_dict() for c in track.clips], snapshot_after)


if __name__ == "__main__":
    unittest.main()


class SetClipFieldCommandTests(unittest.TestCase):
    def test_set_effect_on_several_clips_and_undo(self):
        from easy_movie_studio.commands import SetClipFieldCommand
        track = track_with(4, 4, 4)
        ids = [c.id for c in track.clips]
        command = SetClipFieldCommand(track, ids[:2], "effect", "sepia")
        command.do()
        self.assertEqual([c.effect for c in track.clips], ["sepia", "sepia", None])
        command.undo()
        self.assertEqual([c.effect for c in track.clips], [None, None, None])

    def test_set_brightness_and_undo_restores_per_clip_values(self):
        from easy_movie_studio.commands import SetClipFieldCommand
        track = track_with(4, 4)
        track.clips[1].update(brightness=0.3)
        ids = [c.id for c in track.clips]
        command = SetClipFieldCommand(track, ids, "brightness", -0.2)
        command.do()
        self.assertEqual([c.brightness for c in track.clips], [-0.2, -0.2])
        command.undo()
        self.assertEqual([c.brightness for c in track.clips], [0.0, 0.3])

    def test_invalid_value_leaves_nothing_changed(self):
        from easy_movie_studio.commands import SetClipFieldCommand
        track = track_with(4)
        command = SetClipFieldCommand(track, [track.clips[0].id], "brightness", 5.0)
        with self.assertRaises(ValueError):
            command.do()
        self.assertEqual(track.clips[0].brightness, 0.0)


class SetTransitionCommandTests(unittest.TestCase):
    def test_set_and_undo(self):
        from easy_movie_studio.commands import SetTransitionCommand
        track = track_with(4, 6)
        clip_id = track.clips[1].id
        command = SetTransitionCommand(track, [clip_id], "fade", 1.5)
        command.do()
        self.assertEqual((track.clips[1].transition_in.name, track.clips[1].transition_in.duration),
                         ("fade", 1.5))
        command.undo()
        self.assertIsNone(track.clips[1].transition_in)

    def test_clearing_a_transition(self):
        from easy_movie_studio.commands import SetTransitionCommand
        from easy_movie_studio.model import Transition
        track = track_with(4, 6)
        track.clips[1].transition_in = Transition("dissolve", 2.0)
        command = SetTransitionCommand(track, [track.clips[1].id], None, 1.0)
        command.do()
        self.assertIsNone(track.clips[1].transition_in)
        command.undo()
        self.assertEqual(track.clips[1].transition_in.name, "dissolve")

    def test_apply_to_several_clips(self):
        from easy_movie_studio.commands import SetTransitionCommand
        track = track_with(4, 4, 4)
        ids = [c.id for c in track.clips]
        command = SetTransitionCommand(track, ids, "wipeleft", 0.75)
        command.do()
        self.assertTrue(all(c.transition_in and c.transition_in.name == "wipeleft"
                            for c in track.clips))

    def test_stack_integration(self):
        from easy_movie_studio.commands import SetTransitionCommand, UndoStack
        track = track_with(4, 6)
        clip_id = track.clips[1].id
        stack = UndoStack()
        stack.push(SetTransitionCommand(track, [clip_id], "fade", 1.0))
        self.assertEqual(track.duration, 9.0)  # 4 + 6 - 1 overlap
        stack.undo()
        self.assertEqual(track.duration, 10.0)
        stack.redo()
        self.assertEqual(track.duration, 9.0)


class SetCaptionCommandTests(unittest.TestCase):
    def test_set_and_undo(self):
        from easy_movie_studio.commands import SetCaptionCommand
        track = track_with(5)
        clip_id = track.clips[0].id
        command = SetCaptionCommand(track, clip_id, "Hello", "top")
        command.do()
        self.assertEqual((track.clips[0].caption_text, track.clips[0].caption_position),
                         ("Hello", "top"))
        command.undo()
        self.assertEqual((track.clips[0].caption_text, track.clips[0].caption_position),
                         ("", "bottom"))

    def test_stack_integration_clearing_a_caption(self):
        from easy_movie_studio.commands import SetCaptionCommand, UndoStack
        track = track_with(5)
        clip_id = track.clips[0].id
        track.clips[0].caption_text = "Existing"
        stack = UndoStack()
        stack.push(SetCaptionCommand(track, clip_id, "", "bottom"))
        self.assertEqual(track.clips[0].caption_text, "")
        stack.undo()
        self.assertEqual(track.clips[0].caption_text, "Existing")


class SetAudioMixCommandTests(unittest.TestCase):
    def test_set_and_undo(self):
        from easy_movie_studio.commands import SetAudioMixCommand
        project = Project.new()
        command = SetAudioMixCommand(project, music_volume=0.4, video_volume=1.2,
                                     duck_music=True)
        command.do()
        s = project.settings
        self.assertEqual((s.music_volume, s.video_volume, s.duck_music), (0.4, 1.2, True))
        command.undo()
        self.assertEqual((s.music_volume, s.video_volume, s.duck_music), (1.0, 1.0, False))

    def test_invalid_volume_rejected(self):
        from easy_movie_studio.commands import SetAudioMixCommand
        project = Project.new()
        command = SetAudioMixCommand(project, music_volume=5.0, video_volume=1.0,
                                     duck_music=False)
        with self.assertRaises(ValueError):
            command.do()


class SetClipStartCommandTests(unittest.TestCase):
    def test_set_and_undo(self):
        from easy_movie_studio.commands import SetClipStartCommand
        track = Track(kind="video", ripple=False)
        clip = Clip.from_video("a.mp4", 5.0, start=2.0)
        track.add_clip(clip)
        command = SetClipStartCommand(track, clip.id, 8.0)
        command.do()
        self.assertEqual(clip.start, 8.0)
        command.undo()
        self.assertEqual(clip.start, 2.0)

    def test_negative_start_rejected(self):
        from easy_movie_studio.commands import SetClipStartCommand
        track = Track(kind="video", ripple=False)
        clip = Clip.from_video("a.mp4", 5.0)
        track.add_clip(clip)
        command = SetClipStartCommand(track, clip.id, -1.0)
        with self.assertRaises(ValueError):
            command.do()
        self.assertEqual(clip.start, 0.0)


class SetOverlayCommandTests(unittest.TestCase):
    def test_set_and_undo(self):
        from easy_movie_studio.commands import SetOverlayCommand
        track = Track(kind="video", ripple=False)
        clip = Clip.from_video("a.mp4", 5.0)
        track.add_clip(clip)
        command = SetOverlayCommand(track, clip.id, 0.2, 0.3, 0.5, 0.8)
        command.do()
        self.assertEqual((clip.overlay_x, clip.overlay_y, clip.overlay_scale, clip.opacity),
                         (0.2, 0.3, 0.5, 0.8))
        command.undo()
        self.assertEqual((clip.overlay_x, clip.overlay_y, clip.overlay_scale, clip.opacity),
                         (0.75, 0.75, 0.35, 1.0))

    def test_invalid_scale_rejected(self):
        from easy_movie_studio.commands import SetOverlayCommand
        track = Track(kind="video", ripple=False)
        clip = Clip.from_video("a.mp4", 5.0)
        track.add_clip(clip)
        command = SetOverlayCommand(track, clip.id, 0.5, 0.5, 5.0, 1.0)
        with self.assertRaises(ValueError):
            command.do()
