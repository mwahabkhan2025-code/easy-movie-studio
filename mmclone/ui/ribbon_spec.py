"""Declarative description of the ribbon (tabs, groups, buttons, galleries).

Pure Python (no Qt) so the layout can be tested without a display. The Qt
widgets in ``ribbon.py`` are built from these tuples.

Command ids are dotted strings like ``home.paste``. Menu items and gallery
choices produce ``menu-item-id`` and ``gallery-id/item-id`` respectively.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, Union

REQ_CLIPS = "clips"          # enabled once the project has at least one clip
REQ_SELECTION = "selection"  # enabled once a clip is selected
_VALID_REQUIRES = (None, REQ_CLIPS, REQ_SELECTION)


def is_enabled(requires: Optional[str], has_clips: bool, has_selection: bool) -> bool:
    if requires == REQ_CLIPS:
        return has_clips
    if requires == REQ_SELECTION:
        return has_selection
    return True


@dataclass(frozen=True)
class MenuItem:
    id: str
    text: str


@dataclass(frozen=True)
class Button:
    id: str
    text: str
    icon: str
    menu: Tuple[MenuItem, ...] = ()
    arrow: bool = False  # show a drop-down arrow without a menu of its own
    checkable: bool = False
    checked: bool = False
    requires: Optional[str] = None
    tooltip: str = ""


@dataclass(frozen=True)
class Spin:
    id: str
    label: str
    minimum: float
    maximum: float
    value: float
    step: float = 0.25
    suffix: str = " s"
    requires: Optional[str] = None


@dataclass(frozen=True)
class SmallColumn:
    items: Tuple[Union[Button, Spin], ...]


@dataclass(frozen=True)
class GalleryItem:
    id: str
    text: str
    short: str = ""


@dataclass(frozen=True)
class Gallery:
    id: str
    items: Tuple[GalleryItem, ...]
    visible: int = 4
    tile_w: int = 64
    requires: Optional[str] = None


Slot = Union[Button, SmallColumn, Gallery, Spin]


@dataclass(frozen=True)
class Group:
    title: str
    slots: Tuple[Slot, ...]


@dataclass(frozen=True)
class Tab:
    id: str
    title: str
    groups: Tuple[Group, ...]
    contextual: Optional[str] = None  # header text for a contextual tab


# ---------------------------------------------------------------------------
# Shared lists
# ---------------------------------------------------------------------------
EXPORT_PRESETS: Tuple[GalleryItem, ...] = (
    GalleryItem("recommended", "Recommended for this project", "Best fit"),
    GalleryItem("hq", "High quality (1080p)", "1080p HQ"),
    GalleryItem("standard", "Standard (720p)", "720p"),
    GalleryItem("small", "Small file (480p)", "480p small"),
    GalleryItem("mobile", "Mobile / messaging size limit", "Mobile"),
    GalleryItem("youtube", "YouTube (1080p)", "YouTube"),
    GalleryItem("vertical", "Vertical 9:16 (Reels / Shorts)", "9:16"),
    GalleryItem("audio", "Audio only (MP3)", "MP3"),
    GalleryItem("gif", "Animated GIF", "GIF"),
)

_FADES = tuple(MenuItem(f"edit.{d}.{k}", t) for d in ("fade_in", "fade_out")
               for k, t in (("none", "None"), ("slow", "Slow"), ("medium", "Medium"),
                            ("fast", "Fast")))
_SPEEDS = tuple(MenuItem(f"edit.speed.{k}", t) for k, t in (
    ("8", "8x faster"), ("4", "4x faster"), ("2", "2x faster"), ("1", "Normal (1x)"),
    ("0.5", "0.5x slower"), ("0.25", "0.25x slower"), ("0.125", "0.125x slower")))


def _presets_menu() -> Tuple[MenuItem, ...]:
    return tuple(MenuItem(f"file.save_movie/{p.id}", p.text) for p in EXPORT_PRESETS)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
HOME = Tab("home", "Home", (
    Group("Clipboard", (
        Button("home.paste", "Paste", "mdi6.content-paste"),
        SmallColumn((
            Button("home.cut", "Cut", "mdi6.content-cut", requires=REQ_SELECTION),
            Button("home.copy", "Copy", "mdi6.content-copy", requires=REQ_SELECTION),
        )),
    )),
    Group("Add", (
        Button("home.add_media", "Add videos\nand photos", "mdi6.video-plus"),
        Button("home.add_music", "Add\nmusic", "mdi6.music-note-plus", arrow=True,
               requires=REQ_CLIPS),
        SmallColumn((
            Button("home.webcam", "Webcam video", "mdi6.webcam"),
            Button("home.narration", "Record narration", "mdi6.microphone", arrow=True,
                   requires=REQ_CLIPS),
            Button("home.snapshot", "Snapshot", "mdi6.camera", requires=REQ_CLIPS),
        )),
        SmallColumn((
            Button("home.title", "Title", "mdi6.format-title"),
            Button("home.caption", "Caption", "mdi6.message-text-outline",
                   requires=REQ_SELECTION, tooltip="Caption: adds burned-in text to the "
                   "selected clip"),
            Button("home.credits", "Credits", "mdi6.text-box-multiple-outline", menu=(
                       MenuItem("home.credits.credits", "Credits"),
                       MenuItem("home.credits.director", "Director"),
                       MenuItem("home.credits.cast", "Cast"),
                       MenuItem("home.credits.location", "Location"),
                       MenuItem("home.credits.music", "Music"),
                   )),
        )),
    )),
    Group("AutoMovie themes", (
        Gallery("home.automovie", (
            GalleryItem("contemporary", "Contemporary", "Classic"),
            GalleryItem("pan_zoom", "Pan and zoom", "Pan/Zoom"),
            GalleryItem("fade", "Fade"),
            GalleryItem("cinematic", "Cinematic", "Cinema"),
            GalleryItem("black_white", "Black and white", "B && W"),
        ), visible=4, requires=REQ_CLIPS),
    )),
    Group("Editing", (
        Button("home.rotate_left", "Rotate\nleft", "mdi6.rotate-left", requires=REQ_SELECTION),
        Button("home.rotate_right", "Rotate\nright", "mdi6.rotate-right",
               requires=REQ_SELECTION),
        SmallColumn((
            Button("home.remove", "Remove", "mdi6.close", requires=REQ_SELECTION),
            Button("home.select_all", "Select all", "mdi6.select-all", requires=REQ_CLIPS),
        )),
    )),
    Group("Export", (
        Gallery("home.export_preset", EXPORT_PRESETS, visible=3, requires=REQ_CLIPS),
        Button("home.save_movie", "Save\nmovie", "mdi6.movie-open-check-outline",
               requires=REQ_CLIPS, menu=_presets_menu()),
    )),
))

ANIMATIONS = Tab("animations", "Animations", (
    Group("Transitions", (
        Gallery("anim.transition", (
            GalleryItem("none", "No transition", "None"),
            GalleryItem("fade", "Fade"),
            GalleryItem("dissolve", "Dissolve"),
            GalleryItem("wipe_left", "Wipe left"),
            GalleryItem("wipe_right", "Wipe right"),
            GalleryItem("slide_left", "Slide left"),
            GalleryItem("slide_right", "Slide right"),
            GalleryItem("circle_open", "Circle open"),
            GalleryItem("circle_close", "Circle close"),
            GalleryItem("pixelate", "Pixelate"),
            GalleryItem("radial", "Radial"),
            GalleryItem("zoom_in", "Zoom in"),
        ), visible=6, requires=REQ_SELECTION),
        SmallColumn((
            Spin("anim.duration", "Duration:", 0.25, 5.0, 1.0, requires=REQ_SELECTION),
            Button("anim.transition_all", "Apply to all", "mdi6.check-all",
                   requires=REQ_SELECTION),
        )),
    )),
    Group("Pan and zoom", (
        Gallery("anim.pan_zoom", (
            GalleryItem("none", "No pan and zoom", "None"),
            GalleryItem("auto", "Automatic"),
            GalleryItem("zoom_in", "Zoom in"),
            GalleryItem("zoom_out", "Zoom out"),
            GalleryItem("pan_left", "Pan left"),
            GalleryItem("pan_right", "Pan right"),
            GalleryItem("pan_up", "Pan up"),
            GalleryItem("pan_down", "Pan down"),
        ), visible=6, requires=REQ_SELECTION),
        Button("anim.pan_zoom_all", "Apply to\nall", "mdi6.check-all", requires=REQ_SELECTION),
    )),
))

EFFECTS = Tab("effects", "Visual Effects", (
    Group("Effects", (
        Gallery("fx.effect", (
            GalleryItem("none", "No effect", "None"),
            GalleryItem("cinematic", "Cinematic"),
            GalleryItem("sketch", "Pencil sketch"),
            GalleryItem("warm", "Warm"),
            GalleryItem("pop_art", "Pop art"),
            GalleryItem("grayscale", "Grayscale"),
            GalleryItem("gray_dark", "Grayscale, dark"),
            GalleryItem("gray_light", "Grayscale, light"),
            GalleryItem("negative", "Negative"),
            GalleryItem("cool", "Cool blue"),
            GalleryItem("sepia", "Sepia"),
        ), visible=8, requires=REQ_SELECTION),
        SmallColumn((
            Button("fx.brightness", "Brightness", "mdi6.brightness-6", requires=REQ_SELECTION,
                   menu=(
                       MenuItem("fx.brightness.darker2", "Much darker"),
                       MenuItem("fx.brightness.darker1", "Darker"),
                       MenuItem("fx.brightness.normal", "Normal"),
                       MenuItem("fx.brightness.brighter1", "Brighter"),
                       MenuItem("fx.brightness.brighter2", "Much brighter"),
                   )),
            Button("fx.apply_all", "Apply to all", "mdi6.check-all", requires=REQ_SELECTION),
        )),
    )),
))

PROJECT = Tab("project", "Project", (
    Group("Audio", (
        Button("project.audio_mix", "Audio\nmix", "mdi6.tune-vertical", arrow=True,
               requires=REQ_CLIPS),
        Button("project.fit_music", "Fit to\nmusic", "mdi6.music-note-outline",
               requires=REQ_CLIPS),
    )),
    Group("Aspect ratio", (
        Button("project.aspect", "Aspect\nratio", "mdi6.aspect-ratio", menu=(
            MenuItem("project.aspect.16:9", "Widescreen (16:9)"),
            MenuItem("project.aspect.4:3", "Standard (4:3)"),
            MenuItem("project.aspect.9:16", "Vertical (9:16)"),
            MenuItem("project.aspect.1:1", "Square (1:1)"),
        )),
    )),
))

VIEW = Tab("view", "View", (
    Group("Time zoom", (
        Button("view.zoom_in", "Zoom\nin", "mdi6.magnify-plus-outline"),
        Button("view.zoom_out", "Zoom\nout", "mdi6.magnify-minus-outline"),
        Button("view.zoom_reset", "Reset", "mdi6.magnify-scan"),
    )),
    Group("", (
        Button("view.thumbnail_size", "Thumbnail\nsize", "mdi6.image-size-select-large", menu=(
            MenuItem("view.thumb.xl", "Extra large"),
            MenuItem("view.thumb.l", "Large"),
            MenuItem("view.thumb.m", "Medium"),
            MenuItem("view.thumb.s", "Small"),
        )),
    )),
    Group("", (Button("view.fullscreen", "Preview\nfull screen", "mdi6.fullscreen",
                      requires=REQ_CLIPS),)),
    Group("", (Button("view.waveforms", "Waveforms", "mdi6.waveform", checkable=True,
                      checked=True),)),
))

EDIT = Tab("edit", "Edit", (
    Group("Audio", (
        Button("edit.volume", "Video\nvolume", "mdi6.volume-high", requires=REQ_SELECTION),
        SmallColumn((
            Button("edit.fade_in", "Fade in", "mdi6.trending-up", requires=REQ_SELECTION,
                   menu=tuple(m for m in _FADES if ".fade_in." in m.id)),
            Button("edit.fade_out", "Fade out", "mdi6.trending-down", requires=REQ_SELECTION,
                   menu=tuple(m for m in _FADES if ".fade_out." in m.id)),
        )),
    )),
    Group("Speed", (
        Button("edit.speed", "Speed", "mdi6.speedometer", requires=REQ_SELECTION,
               menu=_SPEEDS),
    )),
    Group("Editing", (
        Button("edit.split", "Split", "mdi6.content-cut", requires=REQ_SELECTION),
        Button("edit.trim", "Trim\ntool", "mdi6.movie-edit-outline", requires=REQ_SELECTION,
               checkable=True, tooltip="Trim tool: drag the clip's edges to trim it"),
        SmallColumn((
            Button("edit.set_start", "Set start point", "mdi6.contain-start",
                   requires=REQ_SELECTION),
            Button("edit.set_end", "Set end point", "mdi6.contain-end",
                   requires=REQ_SELECTION),
        )),
    )),
    Group("", (
        Button("edit.properties", "Properties", "mdi6.information-outline",
               requires=REQ_SELECTION, tooltip="Properties (Alt+Enter)"),
    )),
    Group("", (
        Button("edit.stabilize", "Video\nstabilization", "mdi6.video-stabilization",
               requires=REQ_SELECTION, menu=(
                   MenuItem("edit.stabilize.off", "No stabilization"),
                   MenuItem("edit.stabilize.on", "Stabilize"),
               )),
    )),
), contextual="Video Tools")

TABS: Tuple[Tab, ...] = (HOME, ANIMATIONS, EFFECTS, PROJECT, VIEW, EDIT)

QUICK_ACCESS: Tuple[Tuple[str, str, str], ...] = (
    ("qat.save", "Save project", "mdi6.content-save-outline"),
    ("qat.undo", "Undo", "mdi6.undo"),
    ("qat.redo", "Redo", "mdi6.redo"),
)
