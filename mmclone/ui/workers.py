"""Run slow work (probing files, extracting frames) off the GUI thread.

Results are delivered on the GUI thread: the runnable's signals are connected
to slots of a QObject (the manager) that lives there.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class _Signals(QObject):
    done = Signal(int, object)
    failed = Signal(int, str)


class _Task(QRunnable):
    def __init__(self, task_id: int, fn: Callable[..., Any], args: tuple) -> None:
        super().__init__()
        self.task_id = task_id
        self.fn = fn
        self.args = args
        self.signals = _Signals()
        self.setAutoDelete(False)  # the manager owns the lifetime

    def run(self) -> None:
        try:
            result = self.fn(*self.args)
        except Exception as exc:  # report every failure to the GUI thread
            self.signals.failed.emit(self.task_id, str(exc) or type(exc).__name__)
        else:
            self.signals.done.emit(self.task_id, result)


class TaskManager(QObject):
    def __init__(self, parent: Optional[QObject] = None, max_threads: int = 4) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max_threads)
        self._next_id = 1
        self._tasks: Dict[int, _Task] = {}
        self._callbacks: Dict[int, tuple] = {}

    def submit(self, fn: Callable[..., Any], *args: Any,
               on_done: Callable[[Any], None],
               on_failed: Optional[Callable[[str], None]] = None) -> None:
        task = _Task(self._next_id, fn, args)
        self._next_id += 1
        self._tasks[task.task_id] = task
        self._callbacks[task.task_id] = (on_done, on_failed)
        task.signals.done.connect(self._finished)
        task.signals.failed.connect(self._errored)
        self._pool.start(task)

    def _release(self, task_id: int) -> tuple:
        self._tasks.pop(task_id, None)
        return self._callbacks.pop(task_id, (None, None))

    @Slot(int, object)
    def _finished(self, task_id: int, result: object) -> None:
        on_done, _ = self._release(task_id)
        if on_done is not None:
            on_done(result)

    @Slot(int, str)
    def _errored(self, task_id: int, message: str) -> None:
        _, on_failed = self._release(task_id)
        if on_failed is not None:
            on_failed(message)

    def wait_for_done(self, timeout_ms: int = 5000) -> bool:
        return self._pool.waitForDone(timeout_ms)
