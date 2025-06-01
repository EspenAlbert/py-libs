from __future__ import annotations

import logging
from dataclasses import dataclass, field
from threading import RLock
from typing import Self, TypeVar

from rich.progress import Progress, TaskID

from ask_shell.rich_live import RemoveLivePart, add_renderable, get_live, render_live

logger = logging.getLogger(__name__)
_progress: Progress | None = None
_lock: RLock = RLock()
_remove_progress: RemoveLivePart | None = None


def get_progress() -> Progress:
    global _progress
    if _progress is not None:
        return _progress
    with _lock:
        if _progress is None:
            _progress = Progress(transient=True)
    return _progress


def reset_progress() -> None:
    global _progress

    with _lock:
        if _progress is None:
            return
        if not _progress.finished:
            logger.warning("Resetting progress while it is still running")
        _progress = None


def _add_task(task: new_task):
    global _remove_progress
    with _lock:
        progress = get_progress()
        task._task_id = progress.add_task(
            description=task.description,
            total=task.total,
            visible=task.visible,
            **(task.task_fields or {}),
        )
        if len(progress.tasks) == 1:
            _remove_progress = add_renderable(
                progress, name="Ask Shell Progress", order=-100
            )


def _remove_task(task: new_task):
    global _remove_progress
    with _lock:
        progress = get_progress()
        task_id = task._task_id
        assert task_id is not None, f"Task ID should not be None: {task.description}"
        progress_task = next((t for t in progress.tasks if t.id == task_id), None)
        if not progress_task:
            raise ValueError(
                f"Task ID is None or not found in progress: {task._task_id} for task {task.description}"
            )
        progress.remove_task(task_id)
        if task.print_after_remove:
            table = progress.make_tasks_table([progress_task])
            get_live().console.print(table)
        task._task_id = None
        if not progress.tasks:
            if _remove_progress is not None:
                _remove_progress(print_after_removing=False)
                _remove_progress = None
            reset_progress()


def _advance_task(task: new_task, amount: float = 1.0, total: float | None = None):
    assert task._task_id is not None, f"Task ID should not be None: {task.description}"
    with _lock:
        progress = get_progress()
        progress.update(
            task._task_id,
            advance=amount,
            total=total,
        )
        render_live()


T = TypeVar("T")


@dataclass
class new_task:
    description: str
    total: float = 1
    visible: bool = True
    task_fields: dict | None = None
    print_after_remove: bool = True

    _task_id: TaskID | None = field(init=False, default=None)
    _completed: float = field(init=False, default=0.0)

    @property
    def finished(self) -> bool:
        return self._completed >= self.total

    def __post_init__(self):
        assert self.total > 0, "Total must be greater than 0"

    def __enter__(self) -> Self:
        _add_task(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.complete()  # Ensure we mark it as complete
        _remove_task(self)

    def complete(self) -> None:
        self.advance(self.total, total=self.total)

    def advance(self, amount: float = 1.0, *, total: float | None = None) -> None:
        """
        total: In case the task has increased in size, this is the new total.
        Advance the task by a certain amount.
        For example 1 if total = 100
        Or 0.01 if total = 1
        """
        self._completed += amount
        if total is not None:
            self.total = total
        _advance_task(self, amount, total)
