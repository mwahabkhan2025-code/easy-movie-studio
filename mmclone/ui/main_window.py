"""Main window: ribbon on top, preview + storyboard in the middle, status bar below."""

from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QMainWindow, QMessageBox, QScrollArea, QSlider, QSplitter,
                               QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from .. import APP_NAME
from ..autosave import AutosaveManager
from ..commands import (AddClipsCommand, MoveClipCommand, RemoveClipsCommand,
                        RotateClipsCommand, SetAspectCommand, SetAudioMixCommand,
                        SetCaptionCommand, SetClipFieldCommand, SetClipStartCommand,
                        SetOverlayCommand, SetTransitionCommand, SplitClipCommand,
                        TrimClipCommand, UndoStack)
from ..engine.fit_to_music import compute_fit_to_music
from ..engine.importer import (ImportResult, expand_paths, import_media, insert_position,
                               scan_media, suggest_settings)
from ..engine.probe import AUDIO_EXTS
from ..engine.titles import render_title_png
from ..engine.media_info import MediaInfo
from ..engine.probe import IMAGE_EXTS, VIDEO_EXTS, ProbeError, probe
from ..engine.export import run_export
from ..engine.proxy import ProxyResolver, build_proxy_plan, needs_proxy, proxy_ready
from ..model import PROJECT_EXTENSION, Clip, Project, ProjectFormatError
from ..model.clip import STATIC_KINDS
from ..recent import RecentProjects
from ..settings import AppSettings, SettingsStore
from .file_menu import FileMenuPanel
from .icons import icon
from .audio_mix_dialog import AudioMixDialog
from .export_dialog import SaveMovieDialog
from .file_tools_dialog import CompressVideoDialog, ExtractAudioDialog
from .narration_dialog import NarrationDialog
from .options_dialog import OptionsDialog
from .overlay_dialog import OverlayPositionDialog
from .playback import PlaybackController
from .timeline import TimelineView
from .title_dialogs import _CREDIT_ROLE_HINTS, CaptionDialog, CreditsDialog, TitleDialog
from .preview_pane import FullscreenPreview, PreviewPane
from .properties_dialog import PropertiesDialog
from .ribbon import RibbonBar
from .ribbon_spec import EXPORT_PRESETS, TABS
from .storyboard import StoryboardView
from .thumbcache import ThumbnailCache
from .workers import TaskManager

_FILE_FILTER = f"{APP_NAME} projects (*{PROJECT_EXTENSION})"


def media_file_filter() -> str:
    def pattern(exts) -> str:
        return " ".join("*" + e for e in exts)
    return (f"Videos and photos ({pattern(VIDEO_EXTS + IMAGE_EXTS)});;"
            f"Videos ({pattern(VIDEO_EXTS)});;Photos ({pattern(IMAGE_EXTS)});;All files (*.*)")


def _build_missing_proxies(pending: List[tuple]) -> List[tuple]:
    """Runs off the GUI thread (via TaskManager): builds a low-res proxy for each
    (source_path, MediaInfo) pair that doesn't already have one. Returns the ones that
    failed, as (source_path, error_message) -- one bad file shouldn't stop the rest."""
    failures = []
    for path, info in pending:
        try:
            run_export(build_proxy_plan(path, info))
        except Exception as exc:  # a bad/missing source (ProxyError or otherwise) shouldn't
                                   # abort the rest of the batch
            failures.append((path, str(exc)))
    return failures


class MainWindow(QMainWindow):
    """Top-level window. Commands from the ribbon arrive in ``on_command``."""

    AUTOSAVE_INTERVAL_MS = 60_000

    def __init__(self, project: Optional[Project] = None,
                 recent: Optional[RecentProjects] = None,
                 verify_media: bool = True,
                 settings_store: Optional[SettingsStore] = None,
                 autosave: Optional[AutosaveManager] = None) -> None:
        super().__init__()
        self.recent = recent or RecentProjects()
        self.settings_store = settings_store or SettingsStore()
        self.settings = self.settings_store.load()
        self._apply_ffmpeg_dir_setting()
        self.autosave = autosave or AutosaveManager()
        self.tasks = TaskManager(self)
        self.thumbs = ThumbnailCache(self.tasks, self)
        self.player = PlaybackController(self)
        self.proxy_resolver = ProxyResolver()
        self.player.set_proxy_resolver(self.proxy_resolver.resolve)
        self._generating_proxies = False
        self.fullscreen = FullscreenPreview()
        self.clipboard: List[Clip] = []
        self.undo = UndoStack(on_change=self._on_undo_changed)
        self._transition_duration = 1.0
        self.media: Dict[str, MediaInfo] = {}
        self._verify = verify_media
        self._importing = False
        self._last_dir = ""
        self.setAcceptDrops(True)
        self.project = project or Project.new()
        self.project_path: Optional[str] = None
        self._dirty = False
        self.resize(1280, 800)
        self.setMinimumSize(1200, 640)

        root = QWidget()
        root.setObjectName("centralRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        self.ribbon = RibbonBar(TABS)
        root_layout.addWidget(self.ribbon)

        workspace = QWidget()
        workspace.setObjectName("workspace")
        work_layout = QHBoxLayout(workspace)
        work_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(7)
        splitter.setChildrenCollapsible(False)
        self.preview = PreviewPane()
        self.storyboard = StoryboardView(self.project, self.thumbs)
        story_scroll = QScrollArea()
        story_scroll.setObjectName("storyScroll")
        story_scroll.setWidgetResizable(True)
        story_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        story_scroll.setWidget(self.storyboard)

        self.timeline = TimelineView(self.project)
        timeline_scroll = QScrollArea()
        timeline_scroll.setObjectName("storyScroll")
        timeline_scroll.setWidgetResizable(True)
        timeline_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        timeline_scroll.setWidget(self.timeline)

        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(story_scroll)   # index 0: storyboard
        self.view_stack.addWidget(timeline_scroll)  # index 1: timeline
        splitter.addWidget(self.preview)
        splitter.addWidget(self.view_stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([500, 780])
        work_layout.addWidget(splitter)
        root_layout.addWidget(workspace, 1)

        self._build_status_bar()

        self.file_panel = FileMenuPanel(EXPORT_PRESETS, self)
        self.file_panel.commandTriggered.connect(self.on_command)
        self.ribbon.file_button.clicked.connect(self.show_file_menu)

        self.ribbon.commandTriggered.connect(self.on_command)
        self.ribbon.valueChanged.connect(self._on_value_changed)
        self.storyboard.selectionChanged.connect(self._on_selection_changed)
        self.storyboard.addMediaRequested.connect(lambda: self.on_command("home.add_media"))
        self.storyboard.commandRequested.connect(self.on_command)
        self.storyboard.reorderRequested.connect(self.reorder_clip)
        self.storyboard.trimFinished.connect(self.finish_edge_trim)
        self.storyboard.trimLive.connect(self._on_trim_live)
        self.timeline.commandRequested.connect(self._on_timeline_command)
        self.timeline.moveRequested.connect(self.reposition_clip)
        self.timeline.seekRequested.connect(self.player.seek)
        self.timeline.mediaDropped.connect(self.handle_timeline_drop)
        self.timeline.selectionChanged.connect(
            lambda: self.storyboard.set_selection(self.timeline.selected))
        self.thumbs.ready.connect(self._update_poster)
        self.player.frameReady.connect(self._on_frame)
        self.player.timeChanged.connect(self._on_time)
        self.player.stateChanged.connect(self.preview.set_playing)
        self.player.failed.connect(lambda msg: self.statusBar().showMessage(msg, 5000))
        self.preview.seekRequested.connect(self._on_seek_fraction)
        self.fullscreen.toggleRequested.connect(self.player.toggle)
        self.preview.fullscreenRequested.connect(lambda: self.on_command("view.fullscreen"))
        self.preview.transportPressed.connect(lambda key: self.on_command(f"preview.{key}"))

        self._handlers: Dict[str, Callable[[], None]] = {
            "qat.save": self.save_project,
            "file.new_project": self.new_project,
            "file.open_project": self.open_project,
            "file.save_project": self.save_project,
            "file.save_project_as": self.save_project_as,
            "file.compress_video": self.open_compress_video_dialog,
            "file.extract_audio": self.open_extract_audio_dialog,
            "file.options": self.open_options_dialog,
            "file.about": self.show_about,
            "home.add_media": self.add_media,
            "home.add_music": self.add_music,
            "home.title": self.add_title,
            "home.caption": self.add_caption,
            "home.credits.credits": lambda: self.add_credits("credits"),
            "home.credits.director": lambda: self.add_credits("director"),
            "home.credits.cast": lambda: self.add_credits("cast"),
            "home.credits.location": lambda: self.add_credits("location"),
            "home.credits.music": lambda: self.add_credits("music"),
            "home.narration": self.record_narration,
            "project.audio_mix": self.open_audio_mix,
            "project.fit_music": self.fit_to_music,
            "edit.overlay_position": self.open_overlay_position,
            "preview.play": self.player.toggle,
            "preview.prev": lambda: self.player.step(-1),
            "preview.next": lambda: self.player.step(1),
            "view.fullscreen": self.show_fullscreen,
            "qat.undo": self.do_undo,
            "qat.redo": self.do_redo,
            "home.cut": self.cut_selected,
            "home.copy": self.copy_selected,
            "home.paste": self.paste_clips,
            "edit.split": self.split_selected,
            "edit.trim": self.toggle_trim_tool,
            "edit.set_start": lambda: self.set_trim_point("start"),
            "edit.set_end": lambda: self.set_trim_point("end"),
            "anim.transition_all": self.apply_transition_to_all,
            "anim.pan_zoom_all": lambda: self.apply_field_to_all("pan_zoom"),
            "fx.apply_all": lambda: self.apply_field_to_all("effect"),
            "fx.brightness.darker2": lambda: self.set_field_for_selected("brightness", -0.3),
            "fx.brightness.darker1": lambda: self.set_field_for_selected("brightness", -0.15),
            "fx.brightness.normal": lambda: self.set_field_for_selected("brightness", 0.0),
            "fx.brightness.brighter1": lambda: self.set_field_for_selected("brightness", 0.15),
            "fx.brightness.brighter2": lambda: self.set_field_for_selected("brightness", 0.3),
            "edit.properties": self.show_properties,
            "file.exit": self.close,
            "home.select_all": self.storyboard.select_all,
            "home.remove": self.remove_selected,
            "home.rotate_left": lambda: self.rotate_selected(-90),
            "home.rotate_right": lambda: self.rotate_selected(90),
            "view.zoom_in": lambda: self.zoom_slider.setValue(self.zoom_slider.value() + 10),
            "view.zoom_out": lambda: self.zoom_slider.setValue(self.zoom_slider.value() - 10),
            "view.zoom_reset": lambda: self.zoom_slider.setValue(self.DEFAULT_ZOOM),
            "view.waveforms": self._toggle_waveforms,
        }
        for sequence, command in (("Ctrl+N", "file.new_project"), ("Ctrl+O", "file.open_project"),
                                  ("Ctrl+S", "file.save_project"), ("Ctrl+A", "home.select_all"),
                                  ("Delete", "home.remove"), ("Alt+Return", "edit.properties"),
                                  ("Ctrl+X", "home.cut"), ("Ctrl+C", "home.copy"),
                                  ("Ctrl+V", "home.paste"), ("Ctrl+Z", "qat.undo"),
                                  ("Ctrl+Y", "qat.redo"), ("Ctrl+Shift+Z", "qat.redo")):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(lambda c=command: self.on_command(c))
        space = QShortcut(QKeySequence("Space"), self)
        space.activated.connect(self.player.toggle)

        self._on_undo_changed()
        self.refresh_all()
        self._verify_media()

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(self.AUTOSAVE_INTERVAL_MS)
        self._autosave_timer.timeout.connect(self._autosave_tick)
        self._autosave_timer.start()
        QTimer.singleShot(0, self._check_autosave_recovery)

    DEFAULT_ZOOM = 20

    # ---- status bar -------------------------------------------------------
    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)
        self.item_label = QLabel("")
        self.item_label.setContentsMargins(10, 0, 0, 0)
        bar.addWidget(self.item_label, 1)

        def tool(icon_name: str, tip: str) -> QToolButton:
            button = QToolButton()
            button.setObjectName("zoomBtn")
            button.setIcon(icon(icon_name))
            button.setIconSize(QSize(16, 16))
            button.setToolTip(tip)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            return button

        self.view_toggle = tool("mdi6.view-dashboard-outline", "Storyboard view")
        self.overlay_track_btn = tool("mdi6.picture-in-picture-bottom-right",
                                      "Add an overlay (picture-in-picture) track")
        self.proxy_btn = tool("mdi6.speedometer", "Use proxies for smoother preview playback\n"
                              "(heavy footage only -- export always uses the original files)")
        self.proxy_btn.setCheckable(True)
        self.zoom_out_btn = tool("mdi6.minus-circle-outline", "Zoom out")
        self.zoom_in_btn = tool("mdi6.plus-circle-outline", "Zoom in")
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(1, 100)
        self.zoom_slider.setFixedWidth(110)
        self.zoom_slider.setValue(self.DEFAULT_ZOOM)
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        self.zoom_out_btn.clicked.connect(lambda: self.on_command("view.zoom_out"))
        self.zoom_in_btn.clicked.connect(lambda: self.on_command("view.zoom_in"))
        self.view_toggle.clicked.connect(self.toggle_view)
        self.overlay_track_btn.clicked.connect(self.add_overlay_track)
        self.proxy_btn.toggled.connect(self._toggle_proxies)
        for widget in (self.view_toggle, self.overlay_track_btn, self.proxy_btn,
                      self.zoom_out_btn, self.zoom_slider, self.zoom_in_btn):
            bar.addPermanentWidget(widget)

    def _on_zoom_changed(self, value: int) -> None:
        self.storyboard.set_pps(2.0 + value * 0.6)

    # ---- state refresh ------------------------------------------------------
    def refresh_all(self) -> None:
        self.storyboard.refresh()
        self.timeline.refresh()
        self.player.set_project(self.project)
        settings = self.project.settings
        self.preview.set_aspect(settings.width, settings.height)
        self._on_zoom_changed(self.zoom_slider.value())
        self.update_state()

    def update_state(self) -> None:
        clips = self.storyboard.clips()
        has_clips = bool(clips)
        selected = self.storyboard.selected
        self.ribbon.apply_state(has_clips, bool(selected))
        self.ribbon.set_contextual_visible(bool(selected))
        if len(selected) != 1 and self.ribbon.is_checked("edit.trim"):
            self.ribbon.set_checked("edit.trim", False)
            self.storyboard.set_trim_mode(False)
        if len(selected) == 1:
            clip = self.project.main_track.get_clip(selected[0])
            self.ribbon.set_gallery_current("anim.transition",
                                            clip.transition_in.name if clip.transition_in else "none")
            self.ribbon.set_gallery_current("anim.pan_zoom", clip.pan_zoom or "none")
            self.ribbon.set_gallery_current("fx.effect", clip.effect or "none")
            if clip.transition_in is not None:
                self.ribbon.set_spin_value("anim.duration", clip.transition_in.duration)
        self.preview.set_playable(has_clips)
        self.preview.set_time(self.player.time, self.project.main_track.duration)
        if has_clips:
            index = 0
            if selected:
                ids = [c.id for c in clips]
                index = ids.index(selected[0])
            self.item_label.setText(f"Item {index + 1} of {len(clips)}")
        else:
            self.item_label.setText("")
        self._update_title()
        self._update_poster()

    def _update_title(self) -> None:
        name = self.project.name + ("*" if self._dirty else "")
        self.setWindowTitle(f"{name} - {APP_NAME}")

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._update_title()

    def _on_selection_changed(self) -> None:
        self.update_state()
        if self.storyboard.selected:
            starts = {p.clip.id: p.start for p in self.project.main_track.layout()}
            chosen = [starts[i] for i in self.storyboard.selected if i in starts]
            if chosen:
                self.player.seek(min(chosen))

    def _on_time(self, seconds: float) -> None:
        self.preview.set_time(seconds, self.project.main_track.duration)
        self.timeline.set_time(seconds)

    def _on_seek_fraction(self, fraction: float) -> None:
        self.player.seek(fraction * self.player.duration)

    def _on_frame(self, image) -> None:
        self.preview.set_poster(image)
        self.fullscreen.set_image(image)

    def show_fullscreen(self) -> None:
        if not self.storyboard.clips():
            self.statusBar().showMessage("Add a video or photo first.", 3000)
            return
        image = self.preview.surface.current_image()
        self.fullscreen.set_image(image)
        self.fullscreen.showFullScreen()
        self.fullscreen.setFocus()

    # ---- undo / redo ----------------------------------------------------------
    def _on_undo_changed(self) -> None:
        self.ribbon.set_qat_enabled("qat.undo", self.undo.can_undo)
        self.ribbon.set_qat_enabled("qat.redo", self.undo.can_redo)

    def do_undo(self) -> None:
        if not self.undo.can_undo:
            return
        label = self.undo.undo_label
        self.undo.undo()
        self._after_undo_redo(f"Undid {label}." if label else "Undone.")

    def do_redo(self) -> None:
        if not self.undo.can_redo:
            return
        label = self.undo.redo_label
        self.undo.redo()
        self._after_undo_redo(f"Redid {label}." if label else "Redone.")

    def _after_undo_redo(self, message: str) -> None:
        self._mark_dirty()
        self.refresh_all()
        self.statusBar().showMessage(message, 2500)

    # ---- command dispatch ---------------------------------------------------
    def on_command(self, command: str) -> None:
        handler = self._handlers.get(command)
        if handler is not None:
            handler()
        elif command.startswith("file.open_recent:"):
            self._open_path(command[len("file.open_recent:"):])
        elif command.startswith("project.aspect."):
            self.set_aspect(command[len("project.aspect."):])
        elif command.startswith("view.thumb."):
            self.storyboard.set_thumb_size(command[len("view.thumb."):])
        elif command.startswith("file.save_movie/"):
            self.open_save_movie_dialog(command.split("/", 1)[1])
        elif command.startswith("home.export_preset/"):
            self.open_save_movie_dialog(command.split("/", 1)[1])
        elif command.startswith("anim.transition/"):
            self.set_transition_for_selected(command.split("/", 1)[1])
        elif command.startswith("anim.pan_zoom/"):
            self.set_field_for_selected("pan_zoom", command.split("/", 1)[1])
        elif command.startswith("fx.effect/"):
            self.set_field_for_selected("effect", command.split("/", 1)[1])
        else:
            self._not_available(command)

    def open_save_movie_dialog(self, preset_id: Optional[str] = None) -> None:
        if not self.storyboard.clips():
            self.statusBar().showMessage("Add a video or photo first.", 3000)
            return
        self.player.pause()
        silent = {path for path, info in self.media.items() if not info.has_audio}
        default_dir = os.path.dirname(self.project_path) if self.project_path else ""
        SaveMovieDialog(self.project, silent, default_dir,
                        preset_id or self.settings.default_export_preset, self).exec()

    def open_compress_video_dialog(self) -> None:
        self.player.pause()
        default_dir = os.path.dirname(self.project_path) if self.project_path else ""
        CompressVideoDialog(default_dir, self).exec()

    def open_extract_audio_dialog(self) -> None:
        self.player.pause()
        default_dir = os.path.dirname(self.project_path) if self.project_path else ""
        ExtractAudioDialog(default_dir, self).exec()

    # ---- app-wide preferences (File menu > Options) ----------------------------
    def _apply_ffmpeg_dir_setting(self) -> None:
        """Make an Options-dialog FFmpeg folder override take effect by setting the
        same environment variable engine.tools.find_tool() already checks first."""
        if self.settings.ffmpeg_dir:
            os.environ["MMCLONE_FFMPEG_DIR"] = self.settings.ffmpeg_dir
        else:
            os.environ.pop("MMCLONE_FFMPEG_DIR", None)

    def open_options_dialog(self) -> None:
        dialog = OptionsDialog(self.settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.settings = dialog.values()
        self.settings_store.save(self.settings)
        self._apply_ffmpeg_dir_setting()
        self.statusBar().showMessage("Options saved.", 3000)

    def _not_available(self, command: str) -> None:
        self.statusBar().showMessage(f"'{command}' isn't available yet.", 4000)

    def _on_value_changed(self, widget_id: str, value: float) -> None:
        if widget_id == "anim.duration":
            self._transition_duration = value
            selected = self.storyboard.selected
            if len(selected) == 1:
                clip = self.project.main_track.get_clip(selected[0])
                if clip.transition_in is not None:
                    self.undo.push(SetTransitionCommand(self.project.main_track, selected,
                                                        clip.transition_in.name, value))
                    self._mark_dirty()
                    self.refresh_all()
                    self.storyboard.set_selection(selected)
        else:
            self.statusBar().showMessage(f"{widget_id} = {value:g} (not applied yet)", 3000)

    # ---- editing actions (real, on the model, all undoable) -------------------
    def remove_selected(self) -> None:
        selected = list(self.storyboard.selected)
        if not selected:
            return
        self.undo.push(RemoveClipsCommand(self.project.main_track, selected))
        self.storyboard.set_selection([])
        self._mark_dirty()
        self.refresh_all()

    def rotate_selected(self, degrees: int) -> None:
        ids = list(self.storyboard.selected)
        if not ids:
            return
        self.undo.push(RotateClipsCommand(self.project.main_track, ids, degrees))
        self._mark_dirty()
        self.storyboard.update()
        self._update_poster()

    def set_aspect(self, label: str) -> None:
        self.undo.push(SetAspectCommand(self.project, label))
        self._mark_dirty()
        self.refresh_all()

    def _toggle_waveforms(self) -> None:
        self.storyboard.set_show_waveforms(self.ribbon.is_checked("view.waveforms"))

    # ---- cut / copy / paste ----------------------------------------------------
    def copy_selected(self) -> None:
        ids = set(self.storyboard.selected)
        if not ids:
            return
        ordered = [c for c in self.project.main_track.clips if c.id in ids]
        self.clipboard = [c.duplicate() for c in ordered]
        self.statusBar().showMessage(
            f"Copied {len(self.clipboard)} item(s).", 2500)

    def cut_selected(self) -> None:
        if not self.storyboard.selected:
            return
        self.copy_selected()
        self.remove_selected()

    def paste_clips(self) -> None:
        if not self.clipboard:
            self.statusBar().showMessage("Nothing to paste.", 2500)
            return
        track = self.project.main_track
        new_clips = [c.duplicate() for c in self.clipboard]
        index = insert_position(track, self.storyboard.selected)
        self.undo.push(AddClipsCommand(track, new_clips, index))
        self._mark_dirty()
        self.refresh_all()
        self.storyboard.set_selection([c.id for c in new_clips])
        self.statusBar().showMessage(f"Pasted {len(new_clips)} item(s).", 2500)

    # ---- split --------------------------------------------------------------------
    def split_selected(self) -> None:
        selected = self.storyboard.selected
        if len(selected) != 1:
            self.statusBar().showMessage("Select a single clip to split.", 3000)
            return
        clip_id = selected[0]
        placed = {p.clip.id: (p.start, p.end) for p in self.project.main_track.layout()}
        if clip_id not in placed:
            return
        start, end = placed[clip_id]
        t = self.player.time
        if not (start + 0.03 < t < end - 0.03):
            self.statusBar().showMessage(
                "Move the playhead inside the selected clip, then split.", 3500)
            return
        command = SplitClipCommand(self.project.main_track, clip_id, t)
        self.undo.push(command)
        self._mark_dirty()
        self.refresh_all()
        self.storyboard.set_selection([clip_id])
        self.player.seek(t)

    # ---- trim tool and set start/end point -----------------------------------------
    def toggle_trim_tool(self) -> None:
        checked = self.ribbon.is_checked("edit.trim")
        if checked and len(self.storyboard.selected) != 1:
            self.ribbon.set_checked("edit.trim", False)
            self.statusBar().showMessage("Select a single clip first.", 3000)
            return
        self.storyboard.set_trim_mode(checked)
        if checked:
            self.statusBar().showMessage(
                "Drag the clip's left or right edge to trim it.", 4000)

    def set_trim_point(self, which: str) -> None:
        selected = self.storyboard.selected
        if len(selected) != 1:
            self.statusBar().showMessage("Select a single clip first.", 3000)
            return
        clip_id = selected[0]
        track = self.project.main_track
        clip = track.get_clip(clip_id)
        if clip.media_duration is None:
            self.statusBar().showMessage("Set start/end point works with video clips.", 3000)
            return
        placed = {p.clip.id: p for p in track.layout()}.get(clip_id)
        if placed is None or not (placed.start - 0.001 <= self.player.time <= placed.end + 0.001):
            self.statusBar().showMessage(
                "Move the playhead inside the selected clip first.", 3500)
            return
        source_time = clip.src_in + (self.player.time - placed.start) * clip.speed
        try:
            if which == "start":
                new_in, new_out = source_time, clip.src_out
            else:
                new_in, new_out = clip.src_in, source_time
            self.undo.push(TrimClipCommand(track, clip_id, new_in, new_out))
        except ValueError:
            self.statusBar().showMessage("That point is too close to the other end.", 3000)
            return
        self._mark_dirty()
        self.refresh_all()
        self.storyboard.set_selection([clip_id])

    # ---- animations and visual effects -----------------------------------------
    def set_field_for_selected(self, field_name: str, value) -> None:
        ids = list(self.storyboard.selected)
        if not ids:
            return
        if value == "none":
            value = None
        try:
            self.undo.push(SetClipFieldCommand(self.project.main_track, ids, field_name, value,
                                               label=field_name.replace("_", " ").capitalize()))
        except ValueError:
            self.statusBar().showMessage("That value isn't valid.", 3000)
            return
        self._mark_dirty()
        self.storyboard.update()
        self._update_poster()

    def set_transition_for_selected(self, item_id: str) -> None:
        ids = list(self.storyboard.selected)
        if not ids:
            return
        name = None if item_id == "none" else item_id
        self.undo.push(SetTransitionCommand(self.project.main_track, ids, name,
                                            self._transition_duration))
        self._mark_dirty()
        self.refresh_all()  # the transition changes the track's total duration
        self.storyboard.set_selection(ids)

    def apply_field_to_all(self, field_name: str) -> None:
        selected = self.storyboard.selected
        if len(selected) != 1:
            self.statusBar().showMessage("Select a single clip first.", 3000)
            return
        track = self.project.main_track
        value = getattr(track.get_clip(selected[0]), field_name)
        all_ids = [c.id for c in track.clips]
        self.undo.push(SetClipFieldCommand(track, all_ids, field_name, value,
                                           label="Apply to all"))
        self._mark_dirty()
        self.storyboard.update()
        self._update_poster()

    def apply_transition_to_all(self) -> None:
        selected = self.storyboard.selected
        if len(selected) != 1:
            self.statusBar().showMessage("Select a single clip first.", 3000)
            return
        track = self.project.main_track
        clip = track.get_clip(selected[0])
        name = clip.transition_in.name if clip.transition_in else None
        duration = clip.transition_in.duration if clip.transition_in else self._transition_duration
        all_ids = [c.id for c in track.clips]
        self.undo.push(SetTransitionCommand(track, all_ids, name, duration))
        self._mark_dirty()
        self.refresh_all()
        self.storyboard.set_selection(selected)

    def finish_edge_trim(self, clip_id: str, old_in: float, old_out: float,
                         new_in: float, new_out: float) -> None:
        self.undo.push(TrimClipCommand(self.project.main_track, clip_id, new_in, new_out))
        self._mark_dirty()
        self.refresh_all()
        self.storyboard.set_selection([clip_id])
        if self.ribbon.is_checked("edit.trim"):
            self.storyboard.set_trim_mode(True)

    def _on_trim_live(self) -> None:
        # lightweight refresh while dragging an edge -- avoid a full refresh_all() per pixel
        self.preview.set_time(self.player.time, self.project.main_track.duration)

    # ---- drag to reorder --------------------------------------------------------
    def reorder_clip(self, clip_id: str, new_index: int) -> None:
        self.undo.push(MoveClipCommand(self.project.main_track, clip_id, new_index))
        self._mark_dirty()
        self.refresh_all()
        self.storyboard.set_selection([clip_id])

    # ---- project files ------------------------------------------------------
    def show_file_menu(self) -> None:
        self.file_panel.set_recent(self.recent.items())
        button = self.ribbon.file_button
        self.file_panel.show_at(button.mapToGlobal(QPoint(0, button.height())))

    def _confirm_discard(self) -> bool:
        """Ask what to do with unsaved changes. True means it is fine to continue."""
        if not self._dirty:
            return True
        box = QMessageBox.question(
            self, APP_NAME, f"Do you want to save changes to '{self.project.name}'?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        if box == QMessageBox.StandardButton.Save:
            return self.save_project()
        return box == QMessageBox.StandardButton.Discard

    def _install_project(self, project: Project, path: Optional[str]) -> None:
        self.project = project
        self.project_path = path
        self._dirty = False
        self.media = {}
        self.clipboard = []
        self.undo.clear()
        self.storyboard.set_project(project)
        self.refresh_all()
        self._verify_media()
        self.autosave.clear()  # whatever was pending no longer matches the open project

    def new_project(self) -> None:
        if self._confirm_discard():
            self._install_project(Project.new(), None)

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        start_dir = self._last_dir or self.settings.default_project_dir
        path, _ = QFileDialog.getOpenFileName(self, "Open project", start_dir, _FILE_FILTER)
        if path:
            self._open_path(path, already_confirmed=True)

    def _open_path(self, path: str, already_confirmed: bool = False) -> None:
        if not already_confirmed and not self._confirm_discard():
            return
        try:
            project = Project.load(path)
        except (OSError, ProjectFormatError) as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not open the project.\n\n{exc}")
            self.recent.remove(path)
            return
        project.name = os.path.splitext(os.path.basename(path))[0]
        self._install_project(project, os.path.abspath(path))
        self.recent.add(path)

    def save_project(self) -> bool:
        if self.project_path is None:
            return self.save_project_as()
        return self._write(self.project_path)

    def save_project_as(self) -> bool:
        name = self.project.name + PROJECT_EXTENSION
        if self.project_path:
            suggested = self.project_path
        elif self.settings.default_project_dir:
            suggested = os.path.join(self.settings.default_project_dir, name)
        else:
            suggested = name
        path, _ = QFileDialog.getSaveFileName(self, "Save project as", suggested, _FILE_FILTER)
        if not path:
            return False
        if not path.lower().endswith(PROJECT_EXTENSION):
            path += PROJECT_EXTENSION
        self.project.name = os.path.splitext(os.path.basename(path))[0]
        return self._write(path)

    def _write(self, path: str) -> bool:
        try:
            self.project.save(path)
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not save the project.\n\n{exc}")
            return False
        self.project_path = os.path.abspath(path)
        self._dirty = False
        self.recent.add(path)
        self.autosave.clear()  # the real file is current -- no crash copy needed any more
        self._update_title()
        self.statusBar().showMessage("Project saved.", 3000)
        return True

    # ---- crash-recovery autosave (separate from the project file itself) --------
    def _autosave_tick(self) -> None:
        if self._dirty:
            self.autosave.save(self.project, self.project_path)

    def _check_autosave_recovery(self) -> None:
        info = self.autosave.pending()
        if info is None:
            return
        box = QMessageBox.question(
            self, APP_NAME,
            f"{APP_NAME} didn't close properly last time, and found unsaved work for "
            f"'{info.original_name}'.\n\nDo you want to recover it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if box != QMessageBox.StandardButton.Yes:
            self.autosave.clear()
            return
        try:
            project = self.autosave.recover()
        except (OSError, ProjectFormatError) as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not recover the autosave.\n\n{exc}")
            self.autosave.clear()
            return
        self._install_project(project, info.original_path)
        self._mark_dirty()  # recovered content hasn't been written to original_path yet
        self.statusBar().showMessage("Recovered unsaved work.", 4000)

    def show_about(self) -> None:
        QMessageBox.about(self, f"About {APP_NAME}",
                          f"<b>{APP_NAME}</b><br>A simple video editor inspired by "
                          f"Windows Movie Maker.<br>Early development build.")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._confirm_discard():
            self._autosave_timer.stop()
            self.autosave.clear()  # a clean exit -- whatever was pending is moot
            self.player.shutdown()
            self.fullscreen.close()
            self.tasks.wait_for_done(3000)
            event.accept()
        else:
            event.ignore()

    # ---- importing media ----------------------------------------------------
    def add_media(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Add videos and photos", self._last_dir,
                                                media_file_filter())
        if paths:
            self._last_dir = os.path.dirname(paths[0])
            self.import_files(paths)

    def add_music(self) -> None:
        pattern = " ".join("*" + e for e in AUDIO_EXTS)
        paths, _ = QFileDialog.getOpenFileNames(self, "Add music", self._last_dir,
                                                f"Audio files ({pattern});;All files (*.*)")
        if not paths:
            return
        self._last_dir = os.path.dirname(paths[0])
        result = import_media(expand_paths(paths), allowed_kinds=("audio",))
        if result.errors:
            lines = [f"{os.path.basename(p)}: {reason}" for p, reason in result.errors[:8]]
            QMessageBox.warning(self, APP_NAME, "Some files couldn't be added:\n\n"
                                "\n".join(lines))
        if not result.clips:
            return
        track = next((t for t in self.project.tracks if t.kind == "audio"), None)
        if track is None:
            track = self.project.add_track("audio", "Music", ripple=False)
        start = track.duration
        for clip in result.clips:
            clip.start = start
            start += clip.duration
        self.undo.push(AddClipsCommand(track, result.clips, len(track.clips)))
        self.media.update(result.infos)
        self._mark_dirty()
        self.refresh_all()
        self.statusBar().showMessage(f"Added {len(result.clips)} music file(s).", 4000)

    # ---- timeline view ----------------------------------------------------------
    def toggle_view(self) -> None:
        going_to_timeline = self.view_stack.currentIndex() == 0
        self.view_stack.setCurrentIndex(1 if going_to_timeline else 0)
        if going_to_timeline:
            self.timeline.refresh()
            self.timeline.set_selection(self.storyboard.selected)
            self.timeline.set_time(self.player.time)
            self.view_toggle.setToolTip("Storyboard view")
        else:
            self.storyboard.refresh()
            self.view_toggle.setToolTip("Timeline view")

    def _on_timeline_command(self, command: str) -> None:
        # existing handlers (remove, properties, etc.) all read storyboard.selected, so
        # route every timeline-originated command through the same selection first.
        self.storyboard.set_selection(self.timeline.selected)
        self.on_command(command)

    def reposition_clip(self, clip_id: str, new_start: float) -> None:
        try:
            track, _clip = self.project.find_clip(clip_id)
        except KeyError:
            return
        self.undo.push(SetClipStartCommand(track, clip_id, new_start))
        self._mark_dirty()
        self.refresh_all()
        self.timeline.set_selection([clip_id])

    def handle_timeline_drop(self, track_id: str, start_time: float, paths: list) -> None:
        try:
            track = self.project.get_track(track_id)
        except KeyError:
            return
        paths = expand_paths(paths)
        if not paths:
            return
        allowed = ("video", "image") if track.kind == "video" else ("audio",)
        result = import_media(paths, allowed_kinds=allowed)
        if result.errors:
            lines = [f"{os.path.basename(p)}: {reason}" for p, reason in result.errors[:8]]
            QMessageBox.warning(self, APP_NAME, "Some files couldn't be added:\n\n"
                                "\n".join(lines))
        if not result.clips:
            return
        t = start_time
        for clip in result.clips:
            clip.start = t
            t += clip.duration
        self.undo.push(AddClipsCommand(track, result.clips, len(track.clips)))
        self.media.update(result.infos)
        self._mark_dirty()
        self.refresh_all()
        self.timeline.set_selection([c.id for c in result.clips])

    def add_overlay_track(self) -> None:
        existing = next((t for t in self.project.tracks
                         if t.kind == "video" and t is not self.project.main_track), None)
        if existing is None:
            self.project.add_track("video", "Overlay", ripple=False)
            self._mark_dirty()
            self.refresh_all()
        if self.view_stack.currentIndex() == 0:
            self.toggle_view()
        self.statusBar().showMessage(
            "Overlay track ready -- drop a video or photo onto its row in the timeline.", 5000)

    def open_overlay_position(self) -> None:
        selected = self.storyboard.selected
        if len(selected) != 1:
            self.statusBar().showMessage("Select a single overlay clip first.", 3000)
            return
        try:
            track, clip = self.project.find_clip(selected[0])
        except KeyError:
            return
        if track is self.project.main_track or track.kind != "video":
            self.statusBar().showMessage(
                "Picture-in-picture position only applies to a clip on an overlay video "
                "track.", 4000)
            return
        dialog = OverlayPositionDialog(clip.overlay_x, clip.overlay_y, clip.overlay_scale,
                                       clip.opacity, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        x, y, scale, opacity = dialog.values()
        self.undo.push(SetOverlayCommand(track, clip.id, x, y, scale, opacity))
        self._mark_dirty()
        self.refresh_all()
        self.timeline.set_selection([clip.id])

    # ---- proxy media (preview only; export always uses the original files) ---------
    def _toggle_proxies(self, checked: bool) -> None:
        self.proxy_resolver.enabled = checked
        self.player.set_proxy_resolver(self.proxy_resolver.resolve)  # reopen with/without it
        if not checked:
            self.statusBar().showMessage("Preview now plays the original files.", 3000)
            return
        pending = [(path, info) for path, info in self.media.items()
                  if needs_proxy(info, self.settings.proxy_min_width) and not proxy_ready(path)]
        if not pending:
            self.statusBar().showMessage("Preview now plays proxies where available.", 3000)
            return
        if self._generating_proxies:
            return
        self._generating_proxies = True
        self.statusBar().showMessage(f"Generating {len(pending)} preview prox"
                                     f"{'y' if len(pending) == 1 else 'ies'}...")
        self.tasks.submit(_build_missing_proxies, pending, on_done=self._proxies_built,
                          on_failed=self._proxies_failed)

    def _proxies_built(self, failures: list) -> None:
        self._generating_proxies = False
        self.player.set_proxy_resolver(self.proxy_resolver.resolve)  # pick up new files
        if failures:
            self.statusBar().showMessage(
                f"Proxies ready ({len(failures)} source(s) couldn't be converted).", 5000)
        else:
            self.statusBar().showMessage("Proxies ready -- preview will use them.", 3000)

    def _proxies_failed(self, message: str) -> None:
        self._generating_proxies = False
        self.statusBar().showMessage(f"Couldn't generate proxies: {message}", 5000)

    # ---- audio mix, fit to music, narration -----------------------------------
    def open_audio_mix(self) -> None:
        s = self.project.settings
        dialog = AudioMixDialog(s.music_volume, s.video_volume, s.duck_music, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        music_volume, video_volume, duck_music = dialog.values()
        self.undo.push(SetAudioMixCommand(self.project, music_volume, video_volume, duck_music))
        self._mark_dirty()

    def fit_to_music(self) -> None:
        result = compute_fit_to_music(self.project)
        if result is None:
            self.statusBar().showMessage(
                "Add a clip and some music first, or the movie already matches.", 3500)
            return
        self.undo.push(TrimClipCommand(self.project.main_track, result.clip_id, result.new_in,
                                       result.new_out))
        self._mark_dirty()
        self.refresh_all()
        if result.matched_exactly:
            self.statusBar().showMessage("The movie now matches the music's length.", 3500)
        else:
            self.statusBar().showMessage(
                "Matched as closely as possible -- the last clip ran out of material.", 4500)

    def record_narration(self) -> None:
        dialog = NarrationDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = dialog.result_values()
        if result is None:
            return
        path, duration = result
        try:
            clip = Clip.from_audio(path, duration)
        except ValueError:
            self.statusBar().showMessage("The recording was unusable.", 3000)
            return
        track = next((t for t in self.project.tracks
                     if t.kind == "audio" and t.name == "Narration"), None)
        if track is None:
            track = self.project.add_track("audio", "Narration", ripple=False)
        clip.start = track.duration
        self.undo.push(AddClipsCommand(track, [clip], len(track.clips)))
        self._mark_dirty()
        self.refresh_all()
        self.statusBar().showMessage("Narration added.", 3000)

    # ---- titles, captions, credits -------------------------------------------
    def add_title(self) -> None:
        dialog = TitleDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        text, background, duration = dialog.values()
        if not text.strip():
            self.statusBar().showMessage("Enter some text for the title.", 3000)
            return
        settings = self.project.settings
        path = render_title_png(text, settings.width, settings.height, style="title",
                                background=background)
        clip = Clip.from_title(path, duration, text=text, style="title", background=background)
        track = self.project.main_track
        index = insert_position(track, self.storyboard.selected)
        self.undo.push(AddClipsCommand(track, [clip], index))
        self._mark_dirty()
        self.refresh_all()
        self.storyboard.set_selection([clip.id])

    def add_caption(self) -> None:
        selected = self.storyboard.selected
        if len(selected) != 1:
            self.statusBar().showMessage("Select a single clip first.", 3000)
            return
        track = self.project.main_track
        clip = track.get_clip(selected[0])
        dialog = CaptionDialog(clip.caption_text, clip.caption_position, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        text, position = dialog.values()
        self.undo.push(SetCaptionCommand(track, clip.id, text, position))
        self._mark_dirty()
        self.storyboard.update()

    def add_credits(self, role_key: str) -> None:
        dialog = CreditsDialog(_CREDIT_ROLE_HINTS.get(role_key, ""), parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        lines, background, duration = dialog.values()
        if not lines:
            self.statusBar().showMessage("Enter at least one name.", 3000)
            return
        settings = self.project.settings
        path = render_title_png("", settings.width, settings.height, style="credits",
                                background=background, lines=lines)
        clip = Clip.from_title(path, duration, style="credits", background=background,
                               lines=lines)
        track = self.project.main_track
        self.undo.push(AddClipsCommand(track, [clip], len(track.clips)))  # credits go at the end
        self._mark_dirty()
        self.refresh_all()
        self.storyboard.set_selection([clip.id])

    def import_files(self, paths) -> None:
        paths = expand_paths(paths)
        if not paths:
            return
        if self._importing:
            self.statusBar().showMessage("An import is already running.", 3000)
            return
        self._importing = True
        self.setCursor(Qt.CursorShape.BusyCursor)
        self.statusBar().showMessage(f"Adding {len(paths)} file(s)...")
        self.tasks.submit(import_media, paths, on_done=self._apply_import,
                          on_failed=self._import_failed)

    def _import_finished(self) -> None:
        self._importing = False
        self.unsetCursor()

    def _import_failed(self, message: str) -> None:
        self._import_finished()
        QMessageBox.critical(self, APP_NAME, f"Could not add the files.\n\n{message}")

    def _apply_import(self, result: ImportResult) -> None:
        self._import_finished()
        track = self.project.main_track
        if result.clips:
            was_empty = not track.clips
            index = insert_position(track, self.storyboard.selected)
            self.undo.push(AddClipsCommand(track, result.clips, index))
            self.media.update(result.infos)
            if was_empty:
                label, fps = suggest_settings(result.infos[result.clips[0].source])
                self.project.set_aspect(label)
                if fps:
                    self.project.settings.fps = fps
            self._mark_dirty()
            self.refresh_all()
            self.storyboard.set_selection([c.id for c in result.clips])
            self.statusBar().showMessage(f"Added {len(result.clips)} item(s).", 4000)
        else:
            self.statusBar().clearMessage()
        if result.errors:
            lines = [f"{os.path.basename(p)}: {reason}" for p, reason in result.errors[:8]]
            if len(result.errors) > 8:
                lines.append(f"... and {len(result.errors) - 8} more")
            QMessageBox.warning(self, APP_NAME,
                                "Some files couldn't be added:\n\n" + "\n".join(lines))

    def _verify_media(self) -> None:
        """Probe the project's media in the background and flag unreadable files."""
        if not self._verify:
            return
        paths = [c.source for t in self.project.tracks for c in t.clips]
        if not paths:
            return
        project = self.project
        self.tasks.submit(scan_media, paths,
                          on_done=lambda result, p=project: self._media_scanned(p, result))

    def _media_scanned(self, project: Project, result) -> None:
        if project is not self.project:
            return  # the user opened something else meanwhile
        infos, problems = result
        self.media.update(infos)
        self.storyboard.set_problems(problems)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.import_files(paths)

    # ---- properties and preview poster ----------------------------------------
    def show_properties(self) -> None:
        if not self.storyboard.selected:
            self.statusBar().showMessage("Select a clip first.", 3000)
            return
        clip = self.project.main_track.get_clip(self.storyboard.selected[0])
        info = self.media.get(clip.source)
        error = ""
        if info is None:
            try:
                info = probe(clip.source)
            except ProbeError as exc:
                error = str(exc)
            else:
                self.media[clip.source] = info
        PropertiesDialog(clip.source, info, clip, self.project.settings, error, self).exec()

    def _update_poster(self) -> None:
        if self.player.has_frame:
            return  # live frames from the player take precedence
        clips = self.storyboard.clips()
        if not clips:
            self.preview.set_poster(None)
            return
        clip = next((c for c in clips if c.id in self.storyboard.selected), clips[0])
        if clip.source in self.storyboard.problems:
            self.preview.set_poster(None)
            return
        time = None if clip.kind in STATIC_KINDS else clip.src_in
        self.preview.set_poster(self.thumbs.get(clip.source, time, 540, clip.rotation))

    def settle(self, timeout_ms: int = 8000) -> None:
        """Wait for background work and let the results paint (used for screenshots/tests)."""
        self.tasks.wait_for_done(timeout_ms)
        QApplication.processEvents()
        QApplication.processEvents()

    # ---- screenshots for design review -------------------------------------------
    def capture_screenshots(self, out_dir: str) -> List[str]:
        """Save one PNG per ribbon tab plus the File menu, for comparing with the original."""
        os.makedirs(out_dir, exist_ok=True)
        clips = self.storyboard.clips()
        if clips and not self.storyboard.selected:
            self.storyboard.set_selection([clips[0].id])
        saved: List[str] = []
        self.settle()
        for tab_id in self.ribbon.tab_ids():
            if tab_id == "edit" and not self.ribbon.contextual_visible():
                continue
            self.ribbon.select_tab(tab_id)
            QApplication.processEvents()
            target = os.path.join(out_dir, f"{tab_id}.png")
            self.grab().save(target)
            saved.append(target)
        self.ribbon.select_tab("home")
        self.show_file_menu()
        QApplication.processEvents()
        target = os.path.join(out_dir, "file_menu.png")
        self.file_panel.grab().save(target)
        saved.append(target)
        self.file_panel.hide()
        return saved
