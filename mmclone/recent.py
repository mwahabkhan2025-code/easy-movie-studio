"""Recent projects list, stored as a small JSON file in the user's config folder."""

from __future__ import annotations

import json
import os
from typing import List, Optional

from . import APP_NAME


def default_store_path() -> str:
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") \
        or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_NAME.replace(" ", ""), "recent.json")


class RecentProjects:
    def __init__(self, store_path: Optional[str] = None, limit: int = 10) -> None:
        self.store_path = store_path or default_store_path()
        self.limit = limit

    def _load(self) -> List[str]:
        try:
            with open(self.store_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        return [p for p in data if isinstance(p, str)]

    def _save(self, paths: List[str]) -> None:
        try:
            os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
            with open(self.store_path, "w", encoding="utf-8") as handle:
                json.dump(paths, handle, indent=2)
        except OSError:
            pass  # the recent list is a convenience; never fail because of it

    def items(self) -> List[str]:
        """Most recent first, skipping files that no longer exist."""
        return [p for p in self._load() if os.path.exists(p)]

    def add(self, path: str) -> None:
        path = os.path.abspath(path)
        key = os.path.normcase(path)
        paths = [p for p in self._load() if os.path.normcase(p) != key]
        self._save(([path] + paths)[: self.limit])

    def remove(self, path: str) -> None:
        key = os.path.normcase(os.path.abspath(path))
        self._save([p for p in self._load() if os.path.normcase(p) != key])

    def clear(self) -> None:
        self._save([])
