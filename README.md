# Easy Movie Studio

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/mwahabkhan2025-code/easy-movie-studio/actions/workflows/tests.yml/badge.svg)](https://github.com/mwahabkhan2025-code/easy-movie-studio/actions/workflows/tests.yml)

A free, open-source, Windows Movie Maker style video editor in Python (PySide6 +
FFmpeg), built as a modern replacement now that Movie Maker itself is discontinued.

No AI features, no telemetry, no account required -- just a straightforward multi-clip
video editor: import, trim, transitions, titles/credits, pan & zoom, audio mixing, and
export via FFmpeg with real compression/codec control.

## Contributing

Contributions are welcome -- see [CONTRIBUTING.md](CONTRIBUTING.md) for how the project
is laid out, how to run the tests, and how to open a pull request.

## License

MIT -- see [LICENSE](LICENSE).

## Setup (Windows, Python 3.11, 64-bit)

    git clone https://github.com/mwahabkhan2025-code/easy-movie-studio.git
    cd easy-movie-studio
    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements-dev.txt

## Run

    python -m easy_movie_studio --demo          # window with a made-up project (select a clip to see Video Tools)
    python -m easy_movie_studio                 # empty project
    python -m easy_movie_studio --demo --screenshots shots   # save a PNG of every tab + File menu, then quit

## Test

    pytest
    # or, without pytest installed:
    python -m unittest discover -s tests -t .

## Packaging (a standalone .exe)

    pip install pyinstaller          # already in requirements-dev.txt
    python scripts\build_icon.py     # once, or whenever the app icon design changes
    pyinstaller easy_movie_studio.spec

This produces `dist\EasyMovieStudio\EasyMovieStudio.exe` -- a one-folder build (faster
to start than a single-file `--onefile` build, which matters more for an editor kept
open all session than a smaller installer does). `easy_movie_studio.spec` bundles qtawesome's
icon font and the `ffmpeg.exe` that ships inside `imageio-ffmpeg`, so the folder runs on
a machine with nothing else installed. That bundled FFmpeg build is minimal, though (see "FFmpeg" below) -- for the best
results, drop a full FFmpeg build's `ffmpeg.exe` and `ffprobe.exe` straight into the
`dist\EasyMovieStudio` folder, next to `EasyMovieStudio.exe`. No environment variable or
setup step needed for that to be picked up -- the app's own folder is searched
automatically (right after `EASY_MOVIE_STUDIO_FFMPEG_DIR`, before PATH), specifically so a
packaged build can be made complete by just adding two files. Distribute the whole
`dist\EasyMovieStudio` folder (zipped, or wrapped in an installer with a tool like Inno
Setup) -- `EasyMovieStudio.exe` on its own is missing its PySide6/FFmpeg/font payload.

## Status

- Phase 1a (done): project skeleton, multi-track data model (Clip, Transition,
  Track, Project), JSON save/load with relative media paths, unit tests.
- Phase 1b (done, needs first run on Windows): themed main window, ribbon (Home, Animations,
  Visual Effects, Project, View, contextual Video Tools > Edit), File menu with recent
  projects, preview pane, storyboard with selection, status bar with zoom slider.
  Working now: new/open/save project, select all, remove, rotate, aspect ratio, zoom,
  thumbnail size, waveform toggle. Everything else shows "isn't available yet".
- Phase 2a (done): import videos/photos (button, drag and drop, folders), media probing,
  film-strip thumbnails, poster frame in the preview, Properties dialog (right-click,
  Alt+Enter, Edit tab), project settings picked from the first clip, unreadable/missing
  files flagged on the storyboard.
- Phase 2b (done, needs first run): preview playback. Play/pause (button or Space), seek slider,
  previous/next frame, clips play back to back with speed/volume/rotation, photos play for their
  duration, selecting a clip moves the playhead, full-screen preview (Esc closes, Space toggles).
  Video is decoded by Qt Multimedia; the preview does not blend transitions yet.
- Phase 3 (done, needs first run): editing, all undoable.
  - **Undo/redo**: the quick-access buttons and Ctrl+Z / Ctrl+Y (or Ctrl+Shift+Z), covering
    add (import/paste), remove, rotate, move, trim, split, and aspect ratio changes.
  - **Split**: Edit tab, splits the selected clip at the current playhead position.
  - **Set start point / Set end point**: trims the selected clip using the current playhead.
  - **Trim tool**: a checkable toggle; while a single clip is selected, drag its left or
    right edge directly on the storyboard to trim it live.
  - **Reorder**: drag a clip's body on the storyboard to a new position (works alongside
    the existing click-to-select; a short drag threshold tells a click from a drag).
  - **Cut / Copy / Paste**: Ctrl+X / Ctrl+C / Ctrl+V, or the Home tab buttons. Paste inserts
    fresh copies after the current selection; pasting twice creates independent clips.
- Phase 4 (done): export, via FFmpeg's filter_complex.
  - Every clip is normalized to the project's resolution/fps regardless of its source
    (mixed video sizes, frame rates, and photos all work together).
  - Hard cuts use `concat`; a clip with a transition uses `xfade` (video) + `acrossfade`
    (audio), with the exact overlap and offset Track.layout() already computes for preview.
  - Per-clip rotation, speed (with proper `atempo` chaining for extreme speeds), the
    Visual Effects gallery's look-ups, brightness, volume, and fades are all applied.
  - A clip or photo with no audio gets a generated silent track, so mixed silent/audio
    clips still concatenate cleanly.
  - The Music track is mixed in via `amix`, delayed to each clip's actual start time.
  - Save movie (Home tab button, its preset gallery, and the File menu) opens a dialog:
    preset, CRF quality, encoder speed, an estimated file size, then a cancellable
    progress dialog. Presets: Recommended, 1080p HQ, 720p, 480p small, mobile, YouTube,
    vertical, audio-only (MP3), and animated GIF (palette-optimized).
  - Export runs on a background thread so the window stays responsive.
- Phase 5 (done): Animations and Visual Effects tabs, all undoable, all fully supported by
  the Phase 4 export pipeline already.
  - **Transitions**: pick one from the Animations gallery to set the selected clip's
    incoming transition; "None" clears it. The Duration spinner edits an existing
    transition live, or sets the duration used the next time you pick one. Selecting a
    clip updates the gallery and spinner to show what it already has.
  - **Pan and zoom** and **Effects**: same gallery pattern, selection-synced.
  - **Brightness**: a 5-step preset menu (Much darker .. Much brighter) on the Brightness
    button, since a full slider popup was out of scope for this phase.
  - **Apply to all**: on Animations and Visual Effects, copies the selected clip's
    transition/pan-zoom/effect to every clip on the track.
  - The storyboard shows a small orange chevron on a clip with an incoming transition,
    and a purple dot when an effect, pan/zoom, or brightness change is applied (the
    thumbnail itself doesn't render the effect, so this is the visual cue); hovering a
    clip lists all of this in its tooltip.
- Phase 6a (done): Titles, Credits, Captions, and Add music.
  - **Title**: Home tab button opens a dialog (text, background color, duration) and inserts
    a rendered title card after the current selection (or the project is empty, at the start).
  - **Credits**: the Credits dropdown's five presets (Credits/Director/Cast/Location/Music)
    open the same multi-line role/name editor, pre-filled with a role hint; always appended
    at the end of the movie.
  - Title and credits cards are rendered to PNG with Pillow (`engine/titles.py`, cached by
    content hash) and from then on behave exactly like a photo clip everywhere -- storyboard,
    preview, and export all just see an image, which keeps every other code path unchanged.
  - **Caption**: burns text onto the *selected* clip itself (top/middle/bottom) via FFmpeg's
    `drawtext`. The caption is written to a small cached text file and referenced with
    `textfile=` rather than passed inline, since inline `text=` turned out to mis-parse
    colons and quotes even when escaped (caught by a real FFmpeg run during testing).
  - **Add music**: imports audio files onto the Music track, appended sequentially.
  - The storyboard shows a small orange "CC" tag on a captioned clip, alongside the existing
    transition/effect badges.
- Phase 6b (done): Audio mix, Fit to music, and Record narration.
  - **Audio mix** (Project tab): a dialog with Video volume / Music volume sliders (0-200%)
    and a "duck music" checkbox, stored on the project and applied as a multiplier on top of
    each clip's own volume at export. "Duck music" is a flat attenuation (0.4x) on the whole
    music mix, not a true moment-to-moment sidechain synced to when the video has speech --
    real sidechain ducking was out of scope for this pass; the dialog says so in its tooltip.
  - **Fit to music**: stretches or shrinks the *last* clip on the main track so the movie's
    total length matches the Music track's. A photo or title card has no real length limit,
    so it matches exactly; a real video clip is capped at how much of its source exists, and
    the status bar says so when it can't close the gap completely.
  - **Record narration**: records from the default microphone (via `sounddevice`/`soundfile`)
    into a new "Narration" audio track, kept separate from Music. If no microphone or audio
    library is available, the dialog opens already explaining that and with Record disabled,
    rather than letting you click it and hit a buried error.
  - Along the way, found and fixed a real gap: `ProjectSettings` validated its fields only at
    construction, so a command writing to it directly (like the new audio-mix one) could set
    an out-of-range volume with no error. It now has the same validated `update()` pattern
    `Clip` already used, and `SetAudioMixCommand` was fixed to use it.
- Phase 7 (done): a real multi-track timeline, overlays / picture-in-picture, and snapping.
  - **Timeline view**: a second view of the project (status bar toggle button, next to the
    zoom controls) showing every track as its own row with a time ruler and a playhead,
    instead of just the main track's storyboard. Clicking the ruler seeks; clicking a clip
    selects it (kept in sync with the storyboard's selection either way you switch views).
  - **Add an overlay track**: a new status bar button creates a second video track for
    picture-in-picture. Drop a video or photo directly onto that track's row in the
    timeline to place it there, at the dropped time.
  - **Drag to reposition**: on any non-ripple track (Music, Narration, an overlay track),
    drag a clip left/right in the timeline to move it, with snapping to other clips' edges
    and to the playhead (a real pixel-based catch radius, not just a nearest-neighbor guess).
  - **Picture-in-picture placement**: right-click an overlay clip in the timeline for
    "Picture-in-picture position...", a dialog with position/size/opacity sliders.
    (Positioning goes through this dialog rather than live drag-resize handles on the
    preview canvas -- that was the one deliberate scope cut for this phase.)
  - **Export compositing**: every overlay clip is scaled to its own box (no letterboxing),
    optionally alpha-blended for opacity, and composited onto the base video with FFmpeg's
    `overlay` filter, time-gated to exactly when that clip is on the timeline. Its own audio
    (if any) is mixed in too, delayed to its start time, right alongside Music and Narration.
  - This is the only visual feature in the whole project verified with **real pixel
    sampling**, not just "the export didn't error": solid red/blue test clips, composited,
    then actual pixels read back from the exported file to confirm the overlay appears in
    the right box, at the right time, blends correctly at partial opacity, and two overlay
    clips both show up in sequence.
  - Found and fixed a real latent bug while building this: Music/Narration clips were never
    actually trimmed on export -- `-ss`/`-to` was missing from their FFmpeg input entirely,
    so a trimmed music clip would have silently exported its *whole* source file. No
    existing test had a trimmed music clip, so nothing had caught it until now.
- Phase 8 (done): Compress/Convert video, and Extract audio -- stand-alone file tools that
  work on any file you pick from disk, independent of the current project's storyboard.
  - **File menu > Compress / Convert video**: pick any video file, choose a preset (the
    same Recommended/HQ/Standard/Small/Mobile/YouTube/Vertical ladder as Save Movie), and
    optionally override CRF quality or encoding speed. "Convert format" is the same
    operation -- just save with a different extension (.mp4/.mkv/.mov) to change container.
  - **File menu > Extract audio**: pick a video (or an audio file to simply re-encode it)
    and save just its audio track as an MP3, with a chosen bitrate.
  - Both reuse the exact same, already-tested `build_export_plan`/`resolve_settings`
    pipeline the Save Movie dialog uses, by wrapping the picked file in a throwaway
    one-clip project (`engine/file_tools.py`) -- so compression inherits every fix already
    made to export (even dimensions, silence handling, codec/container choices) instead of
    a second, parallel code path to maintain.
  - Both run on the same cancellable background-thread progress dialog as Save Movie.
  - Explicitly out of scope for this pass (left for a later, focused pass): a batch
    export/convert queue for many files at once, and two-pass encoding to hit an exact
    target file size.
- Phase 9 (done): Pan and zoom finally wired up at export, and preview proxies for
  heavy footage.
  - **Pan and zoom**: the Animations tab's Pan and zoom gallery (Automatic, Zoom in,
    Zoom out, Pan left/right/up/down) existed since Phase 5 and set `clip.pan_zoom`,
    but nothing at export actually read it -- a real gap, found while scoping this
    phase. It's now applied via FFmpeg's `zoompan` filter, animating smoothly across
    the whole clip (a true Ken Burns effect, cropping to fill rather than
    letterboxing), and only on photos and title/credit cards, matching how the
    original Movie Maker scoped the feature.
  - Verified with the same real-pixel-sampling rigor as Phase 7's overlay compositing:
    solid-color and split-color test images, actual frames read back from the exported
    file, confirming all six presets genuinely animate (not just "didn't error") --
    including tracking down a real `zoompan` gotcha along the way (see Fixes below).
  - **Preview proxies**: a status bar toggle (next to the view/overlay buttons) that,
    once turned on, generates a small, fast-encoded copy of every "heavy" video source
    in the project (1080p+ by default) and plays *that* in the preview instead, for
    smoother scrubbing and playback on footage the machine struggles to decode live.
    Proxies are cached on disk by content fingerprint, generated on a background
    thread, and are preview-only -- **export always reads each clip's own original
    file**, proxies or not, so turning this on can never change what gets exported.
  - Deliberately out of scope for this pass: generating proxies automatically on
    import (today it's only the toggle, on demand) and a visible per-file progress
    bar for the batch (today it's a status-bar message while it runs).
- Phase 10 (done): polish -- packaging, crash hardening, preferences, autosave. This
  closes out the planned roadmap; `1.0.0` is the first feature-complete release.
  - **Packaging**: a PyInstaller spec (`easy_movie_studio.spec`) builds a one-folder, console-less
    `MovieStudio` app (`scripts/build_icon.py` generates its multi-resolution `.ico`
    first). Drop `ffmpeg.exe`/`ffprobe.exe` into the build folder and the app finds them
    automatically -- no environment variable needed -- because a packaged `.exe` now
    searches its own folder as part of `engine/tools.py`'s normal lookup order. See
    "Packaging (a standalone .exe)" below for the exact steps.
  - **Crash hardening**: a global exception hook (`easy_movie_studio/crashlog.py`) catches any
    exception that would otherwise silently kill a packaged, console-less `.exe`. It
    writes a timestamped log (app name/version, Python version, platform, full
    traceback) to a per-platform log folder and shows a plain-language dialog with the
    log's location, instead of the window just vanishing.
  - **Options dialog** (File menu > Options): default export preset, default project
    folder, an FFmpeg folder override (for pointing at a specific build), and the
    preview-proxy width threshold. Persisted as a small JSON file
    (`easy_movie_studio/settings.py`, same storage pattern as the recent-projects list) and
    applied live -- the FFmpeg override takes effect immediately via the same
    `EASY_MOVIE_STUDIO_FFMPEG_DIR` environment variable `engine/tools.py` already checks first.
  - **Autosave / crash recovery**: while there are unsaved changes, a background copy
    of the project is written every 60 seconds to a cache folder
    (`easy_movie_studio/autosave.py`) -- separate from the project file chosen with Save/Save As,
    and never touching it. The copy is cleared after a real save or a clean exit, so it
    only ever lingers after a crash or a kill; the next launch offers to recover it.
  - Recent-projects storage (`recent.py`) was already robust from earlier phases
    (missing files are filtered out of the list automatically) and needed no changes.

## Export notes
- FFmpeg's `-ss`/`-to` before `-i` is used for speed (fast seek); on a source with very
  sparse keyframes this can occasionally cut slightly off the exact frame. Re-encoding
  (which this pipeline always does) keeps the rest of the timing accurate.
- The file-size estimate is a rough guide from CRF and bitrate, not a promise -- busy,
  detailed footage compresses worse than plain footage at the same CRF.
- GIF export ignores the Music track (GIFs have no audio) and is capped at a lower
  resolution/fps by default, matching how consumer tools keep GIF files small.

## Fixes since the first Windows run
- Added a real application icon (title bar, taskbar, alt-tab, full-screen preview window),
  generated at runtime from a blue rounded tile plus a white filmstrip glyph.
- AutoMovie theme tiles no longer truncate their labels (Classic, Pan/Zoom, Fade, Cinema, B & W).
- The Properties dialog no longer shows two rows called "Location"; a GPS metadata tag is now
  labelled "GPS coordinates" so it doesn't collide with the file's folder path.

## FFmpeg

`imageio-ffmpeg` bundles `ffmpeg` but not `ffprobe`. Media info therefore uses `ffprobe` when it is
found (folder in EASY_MOVIE_STUDIO_FFMPEG_DIR, then PATH) and otherwise parses the output of `ffmpeg -i`.
Both paths are tested. For the best experience install a full FFmpeg build
(e.g. gyan.dev "full") and put it on PATH; it also adds the stabilization filter used later.

## Layout

    easy_movie_studio/model/   data model, no GUI code (Clip, Track, Project, paths)
    easy_movie_studio/engine/  FFmpeg tools, probe, thumbnails, importer, properties (no Qt)
    easy_movie_studio/ui/      ribbon_spec.py (declarative ribbon), ribbon.py, main_window.py, theme.py ...
    tests/           unit tests (unittest style; pytest runs them too)

## Model notes

- Times are seconds. A clip's timeline length = (src_out - src_in) / speed.
- Ripple tracks (main video) place clips back to back; a transition overlaps
  neighbours, capped at half of each neighbouring clip's length.
- Non-ripple tracks (music, overlays) use each clip's explicit `start`.
- Project files are JSON (`.mmproj`); media paths are stored relative to the file.
