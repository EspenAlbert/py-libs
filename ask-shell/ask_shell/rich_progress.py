from __future__ import annotations

import logging
from dataclasses import dataclass, field
from threading import RLock
from typing import Callable, Self, TypeVar

from rich.progress import Progress, TaskID

from ask_shell.rich_live import RemoveLivePart, add_renderable, get_live, render_live

logger = logging.getLogger(__name__)


def transient_progress() -> Progress:
    return Progress(transient=True)


@dataclass
class ProgressManager:
    """Class that can manage progress tasks and add/remove the renderable progress to the live console when there are no more tasks."""

    title: str = "Ask Shell Progress"
    progress_constructor: Callable[[], Progress] = transient_progress
    _progress: Progress | None = field(init=False, default=None)
    _lock: RLock = field(init=False, default_factory=RLock)
    _remove_progress: RemoveLivePart | None = field(init=False, default=None)

    def get_progress(self) -> Progress:
        if self._progress is not None:
            return self._progress
        with self._lock:
            if self._progress is None:
                self._progress = self.progress_constructor()
        return self._progress

    def reset_progress(self) -> None:
        with self._lock:
            if self._progress is None:
                return
            if not self._progress.finished:
                logger.warning(
                    f"Resetting progress {self.title} while it is still running"
                )
            self._progress = None

    def add_task(self, task: new_task):
        with self._lock:
            progress = self.get_progress()
            task._task_id = progress.add_task(
                description=task.description,
                total=task.total,
                visible=task.visible,
                **(task.task_fields or {}),
            )
            if len(progress.tasks) == 1:
                self._remove_progress = add_renderable(
                    progress, name=self.title, order=-100
                )

    def remove_task(self, task: new_task):
        with self._lock:
            progress = self.get_progress()
            task_id = task._task_id
            assert task_id is not None, (
                f"Task ID should not be None: {task.description}"
            )
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
                if self._remove_progress is not None:
                    self._remove_progress(print_after_removing=False)
                    self._remove_progress = None
                self.reset_progress()

    def update_task(
        self,
        task: new_task,
        *,
        advance: float | None = None,
        total: float | None = None,
        skip_render: bool = False,
        **task_fields,
    ):
        assert task._task_id is not None, (
            f"Task ID should not be None: {task.description}"
        )
        with self._lock:
            progress = self.get_progress()
            progress.update(
                task._task_id,
                advance=advance,
                total=total,
                **task_fields,
            )
            if not skip_render:
                render_live()


progress_manager = ProgressManager()


def get_default_progress_manager() -> ProgressManager:
    return progress_manager


T = TypeVar("T")


@dataclass
class new_task:
    description: str
    total: float = 1
    visible: bool = True
    task_fields: dict = field(default_factory=dict)
    print_after_remove: bool = True
    manager: ProgressManager = field(default_factory=get_default_progress_manager)

    _task_id: TaskID | None = field(init=False, default=None)
    _completed: float = field(init=False, default=0.0)

    @property
    def is_finished(self) -> bool:
        return self._completed >= self.total

    def __post_init__(self):
        assert self.total > 0, "Total must be greater than 0"

    def __enter__(self) -> Self:
        self.manager.add_task(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.complete()  # Ensure we mark it as complete
        self.manager.remove_task(self)

    def complete(self) -> None:
        self.update(advance=self.total, total=self.total)

    def update(
        self, *, advance: float | None = None, total: float | None = None, **task_fields
    ) -> None:
        """
        total: In case the task has increased in size, this is the new total.
        Advance the task by a certain amount.
        For example 1 if total = 100
        Or 0.01 if total = 1
        """
        if advance is not None:
            self._completed += advance
        if total is not None:
            self.total = total
        self.manager.update_task(self, advance=advance, total=total, **task_fields)
