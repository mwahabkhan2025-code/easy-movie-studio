# Contributing to Easy Movie Studio

Thanks for taking a look! Easy Movie Studio is a small, from-scratch video editor, and
contributions of any size are welcome -- bug reports, small fixes, new features, or just
trying it out and filing issues.

## Project layout

    mmclone/model/   data model, no GUI code (Clip, Track, Project, paths)
    mmclone/engine/  FFmpeg tools, probe, thumbnails, importer, properties (no Qt)
    mmclone/ui/      ribbon_spec.py (declarative ribbon), ribbon.py, main_window.py, theme.py ...
    mmclone/commands/  undoable command objects (the undo/redo stack)
    tests/           unit + integration tests (unittest style; pytest runs them too)
    scripts/         one-off dev scripts (e.g. generating the app icon)

The data model and engine packages are plain Python with no Qt dependency, so most of
the logic can be tested without a display. UI code lives only under `mmclone/ui/`.

## Setup

    python -m venv .venv
    .venv\Scripts\activate          # on Windows; `source .venv/bin/activate` on macOS/Linux
    pip install -r requirements-dev.txt

A real FFmpeg/ffprobe install on PATH (or pointed at via `MMCLONE_FFMPEG_DIR`) makes
the integration tests meaningfully more thorough, but isn't required to get started --
`imageio-ffmpeg` bundles a minimal `ffmpeg` binary automatically.

## Running the tests

    pytest
    # or, without pytest installed:
    python -m unittest discover -s tests -t .

Please add or update tests for any change to `mmclone/model/` or `mmclone/engine/` --
that logic is pure Python and cheap to test thoroughly. UI-level tests
(`tests/test_*_ui.py`, suffix by convention) need a real PySide6 install and a display
(or `QT_QPA_PLATFORM=offscreen`); they're skipped automatically when PySide6 isn't
available.

## Making a change

1. Open an issue first for anything beyond a small fix, so the approach can be agreed
   on before you put time into it.
2. Keep pull requests focused -- one feature or fix per PR is much easier to review.
3. Run the full test suite before opening a PR.
4. Describe what you changed and why in the PR description; a short note on how you
   tested it (especially for anything touching FFmpeg export) is appreciated.

## Reporting bugs

Please include: your OS, Python version, the exact steps to reproduce, and -- if the
app crashed -- the crash log it wrote (the dialog shown on crash names its location;
see `mmclone/crashlog.py` for where that is per platform).

## Code style

- No AI features in the app itself -- that's a deliberate project constraint, not an
  oversight.
- Follow the existing patterns: the Command pattern + `UndoStack` for anything that
  mutates a project, `dataclass`-with-`validate()`/`update()` for model/settings
  objects, and the declarative `ribbon_spec.py` for anything that adds a ribbon button.
- Favor pure-Python, Qt-free code in `model/` and `engine/`; keep Qt imports confined to
  `ui/`.
