"""App-wide preferences (File menu > Options), stored as a small JSON file in the
user's config folder -- same storage pattern as recent.py's recent-projects list."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, Optional

from . import APP_NAME
from .engine.export_plan import PRESETS
from .engine.proxy import PROXY_MIN_SOURCE_WIDTH

DEFAULT_EXPORT_PRESET = "recommended"


def default_store_path() -> str:
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") \
        or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_NAME.replace(" ", ""), "settings.json")


@dataclass
class AppSettings:
    default_export_preset: str = DEFAULT_EXPORT_PRESET
    default_project_dir: str = ""       # "" = whatever folder was last used
    ffmpeg_dir: str = ""                # "" = use the normal search order
    proxy_min_width: int = PROXY_MIN_SOURCE_WIDTH

    def validate(self) -> None:
        if self.default_export_preset not in PRESETS:
            raise ValueError(f"Unknown export preset: {self.default_export_preset!r}")
        if self.proxy_min_width < 160:
            raise ValueError("proxy_min_width must be at least 160")

    def update(self, **changes: Any) -> None:
        """Change fields atomically, matching ProjectSettings/Clip's pattern elsewhere:
        if the result is invalid, nothing changes."""
        names = {f.name for f in fields(self)}
        unknown = set(changes) - names
        if unknown:
            raise AttributeError(f"Unknown settings field(s): {sorted(unknown)}")
        old = {name: getattr(self, name) for name in changes}
        for name, value in changes.items():
            setattr(self, name, value)
        try:
            self.validate()
        except ValueError:
            for name, value in old.items():
                setattr(self, name, value)
            raise

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppSettings":
        settings = cls()
        known = {f.name: f.type for f in fields(cls)}
        for name in known:
            if name in data:
                try:
                    setattr(settings, name, type(getattr(settings, name))(data[name]))
                except (TypeError, ValueError):
                    pass  # a corrupted/foreign value for one field shouldn't block the rest
        try:
            settings.validate()
        except ValueError:
            return cls()  # a damaged file falls back to defaults rather than half-applying
        return settings


class SettingsStore:
    def __init__(self, store_path: Optional[str] = None) -> None:
        self.store_path = store_path or default_store_path()

    def load(self) -> AppSettings:
        try:
            with open(self.store_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return AppSettings()
        if not isinstance(data, dict):
            return AppSettings()
        return AppSettings.from_dict(data)

    def save(self, settings: AppSettings) -> None:
        try:
            os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
            with open(self.store_path, "w", encoding="utf-8") as handle:
                json.dump(settings.to_dict(), handle, indent=2)
        except OSError:
            pass  # preferences are a convenience; never fail the app because of them
