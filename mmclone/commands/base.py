"""A small undo/redo stack. Pure Python -- no Qt -- so it's fully unit-testable.

A Command knows how to do() and undo() one change to the model. Pushing a
command onto the stack performs it immediately; undo/redo replay do()/undo()
in the right order. Every push clears the redo list, as in any normal editor.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class Command(Protocol):
    label: str

    def do(self) -> None: ...
    def undo(self) -> None: ...


class UndoStack:
    def __init__(self, on_change: Optional[Callable[[], None]] = None,
                 limit: int = 200) -> None:
        self._undo: List[Command] = []
        self._redo: List[Command] = []
        self._on_change = on_change
        self._limit = limit

    def push(self, command: Command) -> None:
        command.do()
        self._undo.append(command)
        if len(self._undo) > self._limit:
            del self._undo[0]
        self._redo.clear()
        self._changed()

    def undo(self) -> None:
        if not self._undo:
            return
        command = self._undo.pop()
        command.undo()
        self._redo.append(command)
        self._changed()

    def redo(self) -> None:
        if not self._redo:
            return
        command = self._redo.pop()
        command.do()
        self._undo.append(command)
        self._changed()

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
        self._changed()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_label(self) -> Optional[str]:
        return self._undo[-1].label if self._undo else None

    @property
    def redo_label(self) -> Optional[str]:
        return self._redo[-1].label if self._redo else None

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change()
