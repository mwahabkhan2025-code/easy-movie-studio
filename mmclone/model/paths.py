"""Helpers for storing media paths relative to the project file, so a project
folder can be moved or copied to another machine without breaking links."""

from __future__ import annotations

import os
from typing import Optional


def encode_path(path: str, base_dir: Optional[str]) -> str:
    """Return the string to store in the project file."""
    if base_dir is None:
        return path
    try:
        rel = os.path.relpath(path, base_dir)
    except ValueError:  # e.g. different drive on Windows
        return path
    return rel.replace(os.sep, "/")


def decode_path(stored: str, base_dir: Optional[str]) -> str:
    """Turn a stored path back into a usable filesystem path."""
    if base_dir is None or os.path.isabs(stored):
        return stored
    return os.path.normpath(os.path.join(base_dir, stored.replace("/", os.sep)))
