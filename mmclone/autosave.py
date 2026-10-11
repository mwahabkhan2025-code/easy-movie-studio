"""Crash-recovery autosave: a periodic background copy of the open project, kept in a
cache folder -- completely separate from the project file the person chose with File >
Save. ``AutosaveManager.save()`` is called periodically while there are unsaved changes;
``clear()`` removes the leftover after a clean save or a clean exit, so ``pending()``
only ever finds something real to recover from after a crash or a kill."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Optional

from . import APP_NAME
from .model import PROJECT_EXTENSION, Project


def default_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") \
        or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, APP_NAME.replace(" ", ""), "autosave")


@dataclass
class AutosaveInfo:
    original_path: Optional[str]  # where the project was last saved by the person, if ever
    original_name: str
    saved_at: float  # time.time() of the autosave, for "last edited N minutes ago"


class AutosaveManager:
    """One autosave slot per running app instance -- this app edits one project at a
    time, so a single rotating file (plus a small metadata sidecar) is enough."""

    FILE_NAME = "autosave" + PROJECT_EXTENSION
    META_NAME = "autosave.json"

    def __init__(self, directory: Optional[str] = None) -> None:
        self.directory = directory or default_dir()

    @property
    def project_path(self) -> str:
        return os.path.join(self.directory, self.FILE_NAME)

    @property
    def _meta_path(self) -> str:
        return os.path.join(self.directory, self.META_NAME)

    def save(self, project: Project, original_path: Optional[str]) -> None:
        try:
            os.makedirs(self.directory, exist_ok=True)
            project.save(self.project_path)  # itself writes via a temp file + os.replace
            meta = {"original_path": original_path, "original_name": project.name,
                    "saved_at": time.time()}
            tmp = self._meta_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(meta, handle)
            os.replace(tmp, self._meta_path)
        except OSError:
            pass  # autosave is a convenience; never fail the app because of it

    def clear(self) -> None:
        for path in (self.project_path, self._meta_path):
            try:
                os.remove(path)
            except OSError:
                pass

    def pending(self) -> Optional[AutosaveInfo]:
        """A leftover autosave from a previous run that never got to clear(), or None
        if there isn't one or it can't be read. Checked once at startup."""
        try:
            with open(self._meta_path, "r", encoding="utf-8") as handle:
                meta = json.load(handle)
        except (OSError, ValueError):
            return None
        if not isinstance(meta, dict) or not os.path.isfile(self.project_path):
            return None
        original_path = meta.get("original_path")
        if original_path is not None and not isinstance(original_path, str):
            original_path = None
        name = meta.get("original_name")
        if not isinstance(name, str) or not name:
            name = "Untitled"
        saved_at = meta.get("saved_at")
        if not isinstance(saved_at, (int, float)):
            saved_at = 0.0
        return AutosaveInfo(original_path=original_path, original_name=name, saved_at=saved_at)

    def recover(self) -> Project:
        """Load the pending autosave's project data. Raises OSError/ProjectFormatError on
        a damaged file -- callers should treat that the same as "no autosave to offer"."""
        return Project.load(self.project_path)
