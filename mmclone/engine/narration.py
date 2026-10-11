"""Microphone recording for Record Narration.

This needs real audio hardware (and the optional sounddevice/soundfile
packages) to actually record, so every entry point that touches the
microphone is wrapped to turn a missing package, a missing native audio
library, or no input device into a clear RecordingError rather than a crash.
"""

from __future__ import annotations

import os


class RecordingError(Exception):
    """Recording isn't available, or the attempt itself failed."""


# Importing sounddevice can itself raise OSError (not just ImportError) when the
# native PortAudio library isn't installed on the machine -- both need catching.
_IMPORT_ERRORS = (ImportError, OSError)


class NarrationRecorder:
    def __init__(self, sample_rate: int = 48000, channels: int = 1) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self._stream = None
        self._file = None
        self._frames = 0

    @staticmethod
    def available() -> bool:
        """True if recording looks possible: the packages import, PortAudio loads,
        and at least one input device is present. Never raises."""
        try:
            import sounddevice as sd
        except _IMPORT_ERRORS:
            return False
        try:
            import soundfile  # noqa: F401
        except ImportError:
            return False
        try:
            devices = sd.query_devices()
        except Exception:
            return False
        return any(d.get("max_input_channels", 0) > 0 for d in devices)

    @property
    def recording(self) -> bool:
        return self._stream is not None

    @property
    def elapsed(self) -> float:
        return self._frames / self.sample_rate if self._frames else 0.0

    def start(self, path: str) -> None:
        if self._stream is not None:
            raise RecordingError("Already recording.")
        try:
            import sounddevice as sd
        except _IMPORT_ERRORS as exc:
            raise RecordingError("No microphone / audio input is available on this "
                                 "machine.") from exc
        try:
            import soundfile as sf
        except ImportError as exc:
            raise RecordingError("Recording needs the 'soundfile' package "
                                 "(pip install soundfile).") from exc

        try:
            self._file = sf.SoundFile(path, mode="w", samplerate=self.sample_rate,
                                      channels=self.channels, subtype="PCM_16")
        except Exception as exc:
            raise RecordingError(f"Could not create the recording file: {exc}") from exc

        self._frames = 0

        def _callback(indata, frames, time_info, status) -> None:  # pragma: no cover (hardware)
            if self._file is not None:
                self._file.write(indata)
            self._frames += frames

        try:
            self._stream = sd.InputStream(samplerate=self.sample_rate, channels=self.channels,
                                          callback=_callback)
            self._stream.start()
        except Exception as exc:
            self._file.close()
            self._file = None
            raise RecordingError(f"Could not start recording: {exc}") from exc

    def stop(self) -> float:
        """Stops and returns the recorded duration in seconds (0.0 if nothing was recording)."""
        if self._stream is None:
            return 0.0
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None
        duration = self.elapsed
        if self._file is not None:
            self._file.close()
            self._file = None
        return duration

    def cancel(self, path: str) -> None:
        """Stops (if recording) and deletes the partial file, if any."""
        self.stop()
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass
