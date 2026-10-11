"""Builds the FFmpeg command for exporting a project. Pure Python: given a
Project and settings, it returns the exact argument list FFmpeg should run,
without touching the filesystem or a subprocess. That makes the whole export
pipeline testable without ever launching FFmpeg.

The main video track is combined clip by clip: a hard cut uses the `concat`
filter, a clip with an incoming transition uses `xfade` (video) and
`acrossfade` (audio), reusing the exact overlap and start time Track.layout()
already computes -- so preview and export agree on timing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from ..model import Clip, Project, Track
from ..model.clip import STATIC_KINDS

TRANSITION_MAP: Dict[str, str] = {
    "fade": "fade", "dissolve": "dissolve", "wipe_left": "wipeleft",
    "wipe_right": "wiperight", "slide_left": "slideleft", "slide_right": "slideright",
    "circle_open": "circleopen", "circle_close": "circleclose", "pixelate": "pixelize",
    "radial": "radial", "zoom_in": "zoomin",
}

EFFECT_FILTERS: Dict[str, str] = {
    "grayscale": "hue=s=0",
    "gray_dark": "hue=s=0,eq=brightness=-0.15",
    "gray_light": "hue=s=0,eq=brightness=0.15",
    "negative": "negate",
    "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131:0",
    "warm": "colorbalance=rs=0.2:gs=0.05:bs=-0.2",
    "cool": "colorbalance=rs=-0.2:gs=0:bs=0.2",
    "cinematic": "curves=preset=medium_contrast,eq=saturation=1.1",
    "sketch": "edgedetect=mode=colormix:high=0.3",
    "pop_art": "eq=saturation=2.2:contrast=1.3",
}

_ROTATE_FILTERS = {90: "transpose=1", 180: "transpose=2,transpose=2", 270: "transpose=2"}
_CAPTION_Y = {"top": "h*0.06", "middle": "(h-text_h)/2", "bottom": "h*0.88-text_h"}

_PAN_ZOOM_CENTER_X = "(iw-iw/zoom)/2"
_PAN_ZOOM_CENTER_Y = "(ih-ih/zoom)/2"
_PAN_ZOOM_SPAN = 0.22       # how much extra zoom a pan has to play with, pan presets
_PAN_ZOOM_RANGE = 0.25      # how far zoom presets travel (1.0 <-> 1.0 + this)


def _pan_zoom_expressions(name: str, frames: int):
    """Returns (zoom_expr, x_expr, y_expr) for one of the Animations > Pan and zoom
    presets, as FFmpeg `zoompan` filter expressions. ``on`` is zoompan's own output
    frame counter (0..frames-1); progress is linear across the whole clip.

    "auto" plays the same slow zoom-in as "zoom_in" -- Windows Movie Maker's own
    "Automatic" pan/zoom is likewise just a gentle, unsurprising default, not a
    randomized choice.
    """
    progress = f"(on/{max(frames - 1, 1)})"
    if name in ("zoom_in", "auto"):
        zoom = f"1+{_PAN_ZOOM_RANGE}*{progress}"
        return zoom, _PAN_ZOOM_CENTER_X, _PAN_ZOOM_CENTER_Y
    if name == "zoom_out":
        zoom = f"{1 + _PAN_ZOOM_RANGE}-{_PAN_ZOOM_RANGE}*{progress}"
        return zoom, _PAN_ZOOM_CENTER_X, _PAN_ZOOM_CENTER_Y
    zoom = f"{1 + _PAN_ZOOM_SPAN:.3f}"
    if name == "pan_left":
        return zoom, f"(iw-iw/zoom)*(1-{progress})", _PAN_ZOOM_CENTER_Y
    if name == "pan_right":
        return zoom, f"(iw-iw/zoom)*{progress}", _PAN_ZOOM_CENTER_Y
    if name == "pan_up":
        return zoom, _PAN_ZOOM_CENTER_X, f"(ih-ih/zoom)*(1-{progress})"
    if name == "pan_down":
        return zoom, _PAN_ZOOM_CENTER_X, f"(ih-ih/zoom)*{progress}"
    return None


def _pan_zoom_filter(clip: Clip, settings: "ExportSettings") -> Optional[str]:
    """A `zoompan` filter that animates from one framing to another across the whole
    clip -- the Ken Burns effect behind the Animations > Pan and zoom gallery, which
    until now set ``clip.pan_zoom`` without anything at export actually reading it.

    Only applies to still images and title/credit cards (``STATIC_KINDS``), matching
    how the original Movie Maker scoped pan/zoom to photos. zoompan produces its own
    exact ``settings.width``x``settings.height`` output (cropping to fill, never
    letterboxing), so it replaces the usual scale+pad steps for this one clip rather
    than feeding into them.
    """
    if clip.kind not in STATIC_KINDS or not clip.pan_zoom or clip.pan_zoom == "none":
        return None
    frames = max(2, round(clip.duration * settings.fps))
    exprs = _pan_zoom_expressions(clip.pan_zoom, frames)
    if exprs is None:
        return None
    zoom_expr, x_expr, y_expr = exprs
    return (f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':d={frames}:"
           f"s={settings.width}x{settings.height}:fps={settings.fps:g}")


def _escape_ffmpeg_path(path: str) -> str:
    """FFmpeg filter options use ':' as a separator, so a Windows drive letter ('C:') must be
    escaped; backslashes are turned into forward slashes, which FFmpeg accepts on Windows too."""
    return path.replace("\\", "/").replace(":", "\\:")


def _caption_filter(clip: Clip, settings: ExportSettings) -> Optional[str]:
    if not clip.caption_text.strip():
        return None
    # drawtext's own "text=" option needs its OWN escaping on top of the filtergraph's --
    # colons, quotes, and non-ASCII captions are a well-known minefield there (confirmed by
    # a real FFmpeg run during testing: "10:30" inside a single-quoted text= broke parsing
    # even with backslash-escaping applied). "textfile=" sidesteps all of that: the caption
    # is written to its own small file, verbatim, and only the *path* needs escaping.
    from .titles import caption_text_file, find_font_path  # local: keeps Pillow optional

    text_path = caption_text_file(clip.caption_text)
    size = max(16, settings.height // 20)
    y_expr = _CAPTION_Y.get(clip.caption_position, _CAPTION_Y["bottom"])
    parts = [f"drawtext=textfile={_escape_ffmpeg_path(text_path)}", f"fontsize={size}",
             "fontcolor=white", "box=1", "boxcolor=black@0.45", "boxborderw=10",
             "x=(w-text_w)/2", f"y={y_expr}"]
    font_path = find_font_path(bold=False)
    if font_path:
        parts.append(f"fontfile={_escape_ffmpeg_path(font_path)}")
    return ":".join(parts)


class ExportError(Exception):
    """The project can't be exported as it stands (e.g. nothing on the timeline)."""


def even(n: float) -> int:
    """Round to the nearest even integer, at least 2 (most encoders need even dimensions)."""
    value = int(round(n / 2.0)) * 2
    return max(2, value)


@dataclass
class ExportSettings:
    width: int
    height: int
    fps: float = 30.0
    sample_rate: int = 48000
    output_kind: str = "video"       # "video", "audio", or "gif"
    video_codec: str = "libx264"
    crf: int = 20
    speed_preset: str = "medium"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    gif_fps: float = 12.0
    gif_width: int = 480
    video_volume: float = 1.0    # multiplies every main-track clip's own volume
    music_volume: float = 1.0    # multiplies every Music-track clip's own volume
    duck_music: bool = False     # flat attenuation on music; see resolve_settings' docstring


@dataclass
class ExportPreset:
    label: str
    output_kind: str = "video"
    target_height: Optional[int] = None   # None keeps the project's own height
    crf: int = 20
    speed_preset: str = "medium"
    audio_bitrate: str = "192k"
    container: str = "mp4"


PRESETS: Dict[str, ExportPreset] = {
    "recommended": ExportPreset("Recommended for this project"),
    "hq": ExportPreset("High quality (1080p)", target_height=1080, crf=18, speed_preset="slow",
                       audio_bitrate="256k"),
    "standard": ExportPreset("Standard (720p)", target_height=720, crf=21),
    "small": ExportPreset("Small file (480p)", target_height=480, crf=26, audio_bitrate="128k"),
    "mobile": ExportPreset("Mobile / messaging size limit", target_height=480, crf=28,
                           speed_preset="fast", audio_bitrate="96k"),
    "youtube": ExportPreset("YouTube (1080p)", target_height=1080, crf=18, speed_preset="slow",
                            audio_bitrate="256k"),
    "vertical": ExportPreset("Vertical 9:16 (Reels / Shorts)"),
    "audio": ExportPreset("Audio only (MP3)", output_kind="audio", container="mp3",
                          audio_bitrate="192k"),
    "gif": ExportPreset("Animated GIF", output_kind="gif", container="gif"),
}


def resolve_settings(project: Project, preset_id: str) -> ExportSettings:
    preset = PRESETS[preset_id]
    width, height = project.settings.width, project.settings.height
    if preset.target_height and height:
        scale = preset.target_height / height
        width, height = even(width * scale), even(preset.target_height)
    else:
        width, height = even(width), even(height)
    return ExportSettings(width=width, height=height, fps=project.settings.fps,
                          sample_rate=project.settings.sample_rate,
                          output_kind=preset.output_kind, crf=preset.crf,
                          speed_preset=preset.speed_preset, audio_bitrate=preset.audio_bitrate,
                          video_volume=project.settings.video_volume,
                          music_volume=project.settings.music_volume,
                          duck_music=project.settings.duck_music)


def estimate_output_bytes(duration: float, settings: ExportSettings) -> int:
    """A rough size estimate from CRF (via an approximate bits-per-pixel curve) and audio bitrate.

    This is a planning aid, not a promise -- content complexity changes real CRF output size
    a lot -- so callers should present it as "about" a size, never an exact figure.
    """
    if settings.output_kind == "audio":
        audio_kbps = int(settings.audio_bitrate.rstrip("k") or 0)
        return int(duration * audio_kbps * 1000 / 8)
    if settings.output_kind == "gif":
        # crude: ~24 bits per pixel per frame at typical palette compression (~15% of that)
        frame_bytes = settings.gif_width * (settings.gif_width * 9 / 16) * 3 * 0.15
        return int(duration * settings.gif_fps * frame_bytes)
    crf_bits_per_pixel = max(0.02, 0.35 - settings.crf * 0.011)  # empirical, decreases with CRF
    video_bps = settings.width * settings.height * settings.fps * crf_bits_per_pixel
    audio_kbps = int(settings.audio_bitrate.rstrip("k") or 0)
    return int(duration * (video_bps + audio_kbps * 1000) / 8)


def _atempo_chain(speed: float) -> List[str]:
    """FFmpeg's atempo filter only accepts 0.5..2.0, so reaching a bigger factor
    means chaining several of them (their effects multiply)."""
    factors: List[float] = []
    remaining = speed
    while remaining > 2.0 + 1e-9:
        factors.append(2.0)
        remaining /= 2.0
    while remaining < 0.5 - 1e-9:
        factors.append(0.5)
        remaining /= 0.5
    factors.append(remaining)
    return [f"atempo={f:.6f}" for f in factors]


def _video_filters(clip: Clip, settings: ExportSettings) -> str:
    parts: List[str] = []
    if clip.rotation in _ROTATE_FILTERS:
        parts.append(_ROTATE_FILTERS[clip.rotation])
    if abs(clip.speed - 1.0) > 1e-9:
        parts.append(f"setpts={1.0 / clip.speed:.6f}*PTS")
    if clip.effect and clip.effect in EFFECT_FILTERS:
        parts.append(EFFECT_FILTERS[clip.effect])
    if abs(clip.brightness) > 1e-6:
        parts.append(f"eq=brightness={clip.brightness:.3f}")
    pan_zoom = _pan_zoom_filter(clip, settings)
    if pan_zoom:
        # zoompan already outputs the exact target size (cropped to fill, animated),
        # so it stands in for the usual scale+pad letterboxing below rather than
        # feeding into it.
        parts.append(pan_zoom)
        parts.append("setsar=1")
    else:
        parts.append(f"scale={settings.width}:{settings.height}:"
                     f"force_original_aspect_ratio=decrease")
        parts.append(f"pad={settings.width}:{settings.height}:(ow-iw)/2:(oh-ih)/2:color=black")
        parts.append("setsar=1")
        parts.append(f"fps={settings.fps:g}")
    caption = _caption_filter(clip, settings)
    if caption:
        parts.append(caption)
    duration = clip.duration
    if clip.fade_in > 0:
        parts.append(f"fade=t=in:st=0:d={clip.fade_in:.3f}")
    if clip.fade_out > 0:
        parts.append(f"fade=t=out:st={max(0.0, duration - clip.fade_out):.3f}:"
                     f"d={clip.fade_out:.3f}")
    return ",".join(parts)


def _audio_post_filters(clip: Clip, settings: ExportSettings, volume_multiplier: float = 1.0
                        ) -> str:
    parts: List[str] = []
    effective_volume = clip.volume * volume_multiplier
    if abs(effective_volume - 1.0) > 1e-9:
        parts.append(f"volume={effective_volume:.3f}")
    duration = clip.duration
    if clip.fade_in > 0:
        parts.append(f"afade=t=in:st=0:d={clip.fade_in:.3f}")
    if clip.fade_out > 0:
        parts.append(f"afade=t=out:st={max(0.0, duration - clip.fade_out):.3f}:"
                     f"d={clip.fade_out:.3f}")
    parts.append(f"aresample={settings.sample_rate}")
    parts.append("aformat=channel_layouts=stereo")
    return ",".join(parts)


def _audio_filters(clip: Clip, settings: ExportSettings, volume_multiplier: float = 1.0) -> str:
    parts = _atempo_chain(clip.speed) if abs(clip.speed - 1.0) > 1e-9 else []
    rest = _audio_post_filters(clip, settings, volume_multiplier)
    return ",".join(parts + [rest]) if parts else rest


@dataclass
class ExportPlan:
    args: List[str]              # everything after the ffmpeg binary path
    duration: float              # seconds, for progress-percentage math
    output_path: str
    warnings: List[str] = field(default_factory=list)


def _clip_video_input_args(clip: Clip) -> List[str]:
    if clip.kind in STATIC_KINDS:
        return ["-loop", "1", "-t", f"{clip.duration:.6f}", "-i", clip.source]
    return ["-ss", f"{clip.src_in:.6f}", "-to", f"{clip.src_out:.6f}", "-i", clip.source]


def _needs_silence(clip: Clip, silent_sources: FrozenSet[str]) -> bool:
    return clip.kind in STATIC_KINDS or clip.source in silent_sources


def _build_main_track(track: Track, settings: ExportSettings, silent_sources: FrozenSet[str],
                      inputs: List[List[str]], filters: List[str],
                      silence_index: Optional[int], need_video: bool = True,
                      need_audio: bool = True) -> Tuple[Optional[str], Optional[str], float]:
    """Builds only the chains actually needed. FFmpeg's filter_complex rejects any
    declared output pad that nothing consumes, so an audio-only or GIF export must
    never build the side it isn't going to map."""
    placed = track.layout()
    labels = []
    for i, p in enumerate(placed):
        clip = p.clip
        inputs.append(_clip_video_input_args(clip))
        idx = len(inputs) - 1
        v_label = a_label = None
        if need_video:
            v_label = f"v{idx}"
            filters.append(f"[{idx}:v]{_video_filters(clip, settings)}[{v_label}]")
        if need_audio:
            a_label = f"a{idx}"
            if _needs_silence(clip, silent_sources):
                filters.append(f"[{silence_index}:a]atrim=0:{clip.duration:.6f},"
                               f"asetpts=PTS-STARTPTS,"
                               f"{_audio_post_filters(clip, settings, settings.video_volume)}"
                               f"[{a_label}]")
            else:
                filters.append(f"[{idx}:a]{_audio_filters(clip, settings, settings.video_volume)}"
                               f"[{a_label}]")
        labels.append((v_label, a_label))

    cur_v, cur_a = labels[0]
    for i in range(1, len(placed)):
        v_label, a_label = labels[i]
        overlap = placed[i].overlap
        has_transition = overlap > 1e-6 and placed[i].clip.transition_in is not None
        name = (TRANSITION_MAP.get(placed[i].clip.transition_in.name, "fade")
               if has_transition else "")
        out_v = out_a = None
        if need_video:
            out_v = f"x{i}v"
            if has_transition:
                filters.append(f"[{cur_v}][{v_label}]xfade=transition={name}:"
                               f"duration={overlap:.6f}:offset={placed[i].start:.6f}[{out_v}]")
            elif need_audio:
                pass  # combined video+audio concat below covers this case
            else:
                filters.append(f"[{cur_v}][{v_label}]concat=n=2:v=1:a=0[{out_v}]")
        if need_audio:
            out_a = f"x{i}a"
            if has_transition:
                filters.append(f"[{cur_a}][{a_label}]acrossfade=d={overlap:.6f}[{out_a}]")
            elif need_video:
                pass  # combined video+audio concat below covers this case
            else:
                filters.append(f"[{cur_a}][{a_label}]concat=n=2:v=0:a=1[{out_a}]")
        if need_video and need_audio and not has_transition:
            filters.append(f"[{cur_v}][{cur_a}][{v_label}][{a_label}]"
                           f"concat=n=2:v=1:a=1[{out_v}][{out_a}]")
        cur_v, cur_a = out_v, out_a
    return cur_v, cur_a, placed[-1].end if placed else 0.0


DUCK_ATTENUATION = 0.4  # flat music-volume multiplier when "duck music" is on


def _build_extra_audio_tracks(project: Project, settings: ExportSettings,
                              inputs: List[List[str]], filters: List[str]) -> List[str]:
    """Mixes in every dedicated audio track except the main video track (i.e. Music and
    Narration), each clip trimmed to its own in/out points and delayed to its real start
    time. Overlay video tracks' own audio is handled separately, in _build_overlay_tracks,
    since each needs only ONE input shared between its video and its audio.

    "Duck music" is a flat volume reduction applied to the whole music mix, not a
    true time-varying sidechain duck synced to where the video's own audio is
    actually present -- real sidechain ducking was out of scope for this pass.
    """
    multiplier = settings.music_volume * (DUCK_ATTENUATION if settings.duck_music else 1.0)
    labels: List[str] = []
    for track in project.tracks:
        if track is project.main_track or track.kind != "audio":
            continue
        for p in track.layout():
            clip = p.clip
            inputs.append(["-ss", f"{clip.src_in:.6f}", "-to", f"{clip.src_out:.6f}",
                           "-i", clip.source])
            idx = len(inputs) - 1
            label = f"m{idx}"
            delay_ms = max(0, round(p.start * 1000))
            filters.append(f"[{idx}:a]{_audio_filters(clip, settings, multiplier)},"
                           f"adelay={delay_ms}|{delay_ms}[{label}]")
            labels.append(label)
    return labels


def _overlay_video_filters(clip: Clip, settings: ExportSettings) -> str:
    """Like _video_filters, but scales to the overlay's own small box (preserving aspect,
    no letterbox padding) instead of filling the whole frame, and applies opacity."""
    parts: List[str] = []
    if clip.rotation in _ROTATE_FILTERS:
        parts.append(_ROTATE_FILTERS[clip.rotation])
    if abs(clip.speed - 1.0) > 1e-9:
        parts.append(f"setpts={1.0 / clip.speed:.6f}*PTS")
    if clip.effect and clip.effect in EFFECT_FILTERS:
        parts.append(EFFECT_FILTERS[clip.effect])
    if abs(clip.brightness) > 1e-6:
        parts.append(f"eq=brightness={clip.brightness:.3f}")
    box_width = max(2, even(settings.width * clip.overlay_scale))
    parts.append(f"scale={box_width}:-2")
    parts.append("setsar=1")
    parts.append(f"fps={settings.fps:g}")
    if clip.opacity < 1.0 - 1e-6:
        parts.append("format=rgba")
        parts.append(f"colorchannelmixer=aa={clip.opacity:.3f}")
    return ",".join(parts)


def _build_overlay_tracks(project: Project, settings: ExportSettings,
                          silent_sources: FrozenSet[str], inputs: List[List[str]],
                          filters: List[str], silence_index: Optional[int], base_v: str
                          ) -> Tuple[str, List[str]]:
    """Composites every non-main VIDEO track (picture-in-picture / overlays) on top of
    ``base_v``, one clip at a time, and collects each clip's own audio (delayed to its
    start time) to be mixed in alongside Music/Narration. Returns (new_base_v, audio_labels).
    """
    current_v = base_v
    audio_labels: List[str] = []
    for track in project.tracks:
        if track is project.main_track or track.kind != "video":
            continue
        for p in track.layout():
            clip = p.clip
            inputs.append(_clip_video_input_args(clip))
            idx = len(inputs) - 1
            ov_label = f"ov{idx}"
            filters.append(f"[{idx}:v]{_overlay_video_filters(clip, settings)}[{ov_label}]")
            next_v = f"ovc{idx}"
            x_expr = f"(main_w*{clip.overlay_x:.4f})-(overlay_w/2)"
            y_expr = f"(main_h*{clip.overlay_y:.4f})-(overlay_h/2)"
            filters.append(f"[{current_v}][{ov_label}]overlay=x={x_expr}:y={y_expr}:"
                           f"enable='between(t,{p.start:.6f},{p.end:.6f})'[{next_v}]")
            current_v = next_v

            a_label = f"ova{idx}"
            if _needs_silence(clip, silent_sources):
                filters.append(f"[{silence_index}:a]atrim=0:{clip.duration:.6f},"
                               f"asetpts=PTS-STARTPTS,"
                               f"{_audio_post_filters(clip, settings, settings.video_volume)}"
                               f"[{a_label}]")
            else:
                filters.append(f"[{idx}:a]{_audio_filters(clip, settings, settings.video_volume)}"
                               f"[{a_label}]")
            delay_ms = max(0, round(p.start * 1000))
            delayed_label = f"ovad{idx}"
            filters.append(f"[{a_label}]adelay={delay_ms}|{delay_ms}[{delayed_label}]")
            audio_labels.append(delayed_label)
    return current_v, audio_labels


def _clips_needing_silence_check(project: Project, settings: ExportSettings):
    """Every clip that could end up routed through the shared silence input, across
    whichever tracks this particular export actually uses (mirrors the track selection
    logic in build_export_plan, so the silence input is reserved exactly when needed)."""
    yield from (p.clip for p in project.main_track.layout())
    if settings.output_kind != "gif":
        for track in project.tracks:
            if track is project.main_track or track.kind != "audio":
                continue
            yield from (p.clip for p in track.layout())
    if settings.output_kind == "video":
        for track in project.tracks:
            if track is project.main_track or track.kind != "video":
                continue
            yield from (p.clip for p in track.layout())


def build_export_plan(project: Project, output_path: str, settings: ExportSettings,
                      silent_sources: Optional[Set[str]] = None) -> ExportPlan:
    silent = frozenset(silent_sources or ())
    placed = project.main_track.layout()
    if not placed:
        raise ExportError("There's nothing on the timeline to export.")

    inputs: List[List[str]] = []
    filters: List[str] = []
    # Reserve the shared silence input's slot *before* any per-clip inputs, so every
    # later "[N:a]"/"[N:v]" reference can use its real, final index right away --
    # no re-indexing pass needed once other inputs are appended.
    need_video = settings.output_kind in ("video", "gif")
    need_audio = settings.output_kind in ("video", "audio")

    silence_index: Optional[int] = None
    if need_audio and any(_needs_silence(c, silent)
                          for c in _clips_needing_silence_check(project, settings)):
        inputs.append(["-f", "lavfi", "-i",
                       f"anullsrc=channel_layout=stereo:sample_rate={settings.sample_rate}"])
        silence_index = 0

    final_v, final_a, duration = _build_main_track(project.main_track, settings, silent,
                                                    inputs, filters, silence_index,
                                                    need_video=need_video, need_audio=need_audio)

    warnings: List[str] = []
    has_overlay_tracks = any(t is not project.main_track and t.kind == "video" and t.clips
                             for t in project.tracks)
    if settings.output_kind == "video":
        if has_overlay_tracks:
            final_v, overlay_audio = _build_overlay_tracks(project, settings, silent, inputs,
                                                            filters, silence_index, final_v)
        else:
            overlay_audio = []
        extra = _build_extra_audio_tracks(project, settings, inputs, filters) + overlay_audio
        if extra:
            all_audio = [final_a] + extra
            mix_in = "".join(f"[{l}]" for l in all_audio)
            filters.append(f"{mix_in}amix=inputs={len(all_audio)}:duration=first:"
                           f"dropout_transition=0,volume={len(all_audio)}[mixed]")
            final_a = "mixed"
    elif settings.output_kind == "audio":
        extra = _build_extra_audio_tracks(project, settings, inputs, filters)
        if extra:
            all_audio = [final_a] + extra
            mix_in = "".join(f"[{l}]" for l in all_audio)
            filters.append(f"{mix_in}amix=inputs={len(all_audio)}:duration=first:"
                           f"dropout_transition=0,volume={len(all_audio)}[mixed]")
            final_a = "mixed"
        if has_overlay_tracks:
            warnings.append("Picture-in-picture video is not included in an audio-only export "
                            "(its own audio isn't either).")
    else:  # gif
        warnings.append("Music tracks and picture-in-picture video are not included in an "
                        "animated GIF.")

    flat_inputs: List[str] = [arg for one in inputs for arg in one]

    if settings.output_kind == "audio":
        args = flat_inputs + ["-filter_complex", ";".join(filters), "-map", f"[{final_a}]",
                              "-vn", "-c:a",
                              "libmp3lame" if output_path.lower().endswith(".mp3") else "aac",
                              "-b:a", settings.audio_bitrate, "-y", output_path]
    elif settings.output_kind == "gif":
        filters.append(f"[{final_v}]fps={settings.gif_fps:g},"
                       f"scale={settings.gif_width}:-2:flags=lanczos,split[gs0][gs1]")
        filters.append("[gs0]palettegen=stats_mode=diff[gp]")
        filters.append("[gs1][gp]paletteuse=dither=bayer[gout]")
        args = flat_inputs + ["-filter_complex", ";".join(filters), "-map", "[gout]",
                              "-y", output_path]
    else:
        args = flat_inputs + ["-filter_complex", ";".join(filters), "-map", f"[{final_v}]",
                              "-map", f"[{final_a}]", "-c:v", settings.video_codec,
                              "-crf", str(settings.crf), "-preset", settings.speed_preset,
                              "-pix_fmt", "yuv420p", "-r", f"{settings.fps:g}",
                              "-c:a", settings.audio_codec, "-b:a", settings.audio_bitrate,
                              "-movflags", "+faststart", "-y", output_path]

    return ExportPlan(args=args, duration=duration, output_path=output_path, warnings=warnings)

