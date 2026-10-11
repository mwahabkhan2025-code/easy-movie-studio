"""Tests the graceful-failure paths for real -- this sandbox genuinely has no PortAudio
library and no 'soundfile' package, so these exercise the actual missing-hardware code
path rather than a mock of it. Real microphone capture itself cannot be verified here;
see the project README for what that means for this feature."""

import os
import tempfile
import unittest

from easy_movie_studio.engine.narration import NarrationRecorder, RecordingError


class AvailabilityTests(unittest.TestCase):
    def test_available_never_raises_and_returns_a_bool(self):
        result = NarrationRecorder.available()
        self.assertIsInstance(result, bool)


class StartStopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.tmp, ignore_errors=True)
        self.path = os.path.join(self.tmp, "narration.wav")

    def test_start_without_hardware_raises_recording_error_not_a_raw_exception(self):
        recorder = NarrationRecorder()
        with self.assertRaises(RecordingError):
            recorder.start(self.path)
        self.assertFalse(recorder.recording)  # failed start leaves a clean state

    def test_stop_without_starting_is_a_safe_no_op(self):
        recorder = NarrationRecorder()
        self.assertEqual(recorder.stop(), 0.0)

    def test_double_stop_is_safe(self):
        recorder = NarrationRecorder()
        recorder.stop()
        recorder.stop()  # should not raise

    def test_cancel_without_starting_does_not_raise(self):
        recorder = NarrationRecorder()
        recorder.cancel(self.path)  # no file, no stream -- should be a no-op

    def test_cancel_removes_an_existing_partial_file(self):
        recorder = NarrationRecorder()
        with open(self.path, "wb") as handle:
            handle.write(b"partial wav data")
        self.assertTrue(os.path.isfile(self.path))
        recorder.cancel(self.path)
        self.assertFalse(os.path.isfile(self.path))

    def test_elapsed_is_zero_before_recording(self):
        recorder = NarrationRecorder()
        self.assertEqual(recorder.elapsed, 0.0)

    def test_failed_start_does_not_leave_a_dangling_file_handle(self):
        # if sounddevice/soundfile were available but PortAudio's InputStream failed,
        # the half-created SoundFile should be closed and cleared, not leaked
        recorder = NarrationRecorder()
        try:
            recorder.start(self.path)
        except RecordingError:
            pass
        self.assertIsNone(recorder._file)
        self.assertIsNone(recorder._stream)


if __name__ == "__main__":
    unittest.main()
