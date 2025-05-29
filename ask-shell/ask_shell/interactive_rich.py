from __future__ import annotations

import functools
import logging
from dataclasses import dataclass, field
from typing import Callable, NamedTuple, Self, TypeVar

from rich.console import Console
from rich.live import Live
from rich.progress import Progress as RichProgress
from rich.progress import ProgressColumn, Task, TaskID

logger = logging.getLogger(__name__)
_progress: Progress | None = None


class GroupedTasks(NamedTuple):
    finished: list[Task]
    in_progress: list[Task]


class Progress(RichProgress):
    def __init__(
        self,
        *columns: str | ProgressColumn,
        console: Console | None = None,
        auto_refresh: bool = True,
        refresh_per_second: float = 10,
        speed_estimate_period: float = 30,
        transient: bool = False,
        get_time: Callable[[], float] | None = None,
        disable: bool = False,
        expand: bool = False,
    ) -> None:
        global _progress
        if _progress is not None:
            raise RuntimeError(
                "Progress instance already created, multiple progresses not allowed. Use get_progress() to access it."
            )
        super().__init__(
            *columns,
            console=console,
            auto_refresh=auto_refresh,
            refresh_per_second=refresh_per_second,
            speed_estimate_period=speed_estimate_period,
            transient=transient,
            redirect_stdout=False,
            redirect_stderr=False,
            get_time=get_time,
            disable=disable,
            expand=expand,
        )
        _progress = self

    def __enter__(self) -> Self:
        """Should not rely on the global _progress variable, but rather use get_progress()"""
        global _progress
        if _progress and _progress is not self:
            raise RuntimeError("Competing global progress instance detected.")
        _progress = self
        old_live = self.live
        self.live = Live(
            console=self.console,
            auto_refresh=old_live.auto_refresh,
            refresh_per_second=old_live.refresh_per_second,
            transient=old_live.transient,
            redirect_stdout=False,
            redirect_stderr=False,
            get_renderable=old_live.get_renderable,
        )
        return super().__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        super().__exit__(exc_type, exc_val, exc_tb)
        if _progress is self:
            reset_progress()

    def grouped_tasks(self) -> GroupedTasks:
        """
        Returns a tuple of finished and in_progress tasks.
        """
        finished, in_progress = [], []
        for task in self.tasks:
            if task.finished:
                finished.append(task)
            else:
                in_progress.append(task)
        return GroupedTasks(finished=finished, in_progress=in_progress)

    def set_tasks(self, tasks: list[Task]) -> None:
        with self._lock:
            self._tasks = {task.id: task for task in tasks}
            self.refresh()


def get_progress() -> Progress | None:
    return _progress


def reset_progress() -> None:
    global _progress
    if _progress is not None and not _progress.finished:
        logger.warning("Resetting progress while it is still running")
    _progress = None


T = TypeVar("T")


def ensure_progress_stopped(func: T) -> T:
    """Decorator to ensure that the stdout is "free" from progress updates during the function execution.
    This is useful for input functions in interactive module."""

    @functools.wraps(func)  # type: ignore
    def wrapper(*args, **kwargs):
        progress = get_progress()
        if progress is None:
            return func(*args, **kwargs)  # type: ignore
        _, in_progress_tasks = progress.grouped_tasks()
        for task in in_progress_tasks:
            progress.remove_task(task.id)
        progress.refresh()
        progress.__exit__(
            None, None, None
        )  # we need to ensure the live content is logged to the console
        try:
            return func(*args, **kwargs)  # type: ignore
        except Exception as e:
            raise e
        finally:
            progress.set_tasks(in_progress_tasks)
            progress.__enter__()  # ensure the live content is restored but only with tasks in progress

    return wrapper  # type: ignore


@dataclass
class new_task:
    description: str
    total: int = 1
    visible: bool = True
    task_fields: dict | None = None

    _task_id: TaskID | None = field(init=False, default=None)
    _completed: float = field(init=False, default=0.0)

    @property
    def finished(self) -> bool:
        progress_task_id = self._ensure_progress_and_task_id()
        if progress_task_id is None:
            raise RuntimeError(
                f"Progress instance not created. Must have an active progress to check task status. (description: {self.description})"
            )
        progress, task_id = progress_task_id
        return progress.tasks[task_id].finished

    def __post_init__(self):
        assert self.total > 0, "Total must be greater than 0"

    def __enter__(self) -> Self:
        progress = get_progress()
        if progress is None:
            raise RuntimeError(
                f"Progress instance not created. Must have an active progress to enter a task. (description: {self.description})"
            )
        self._task_id = progress.add_task(
            description=self.description,
            start=True,
            total=self.total,
            visible=self.visible,
            **(self.task_fields or {}),
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.complete()  # Ensure we mark it as complete
        progress_task_id = self._ensure_progress_and_task_id()
        if progress_task_id is None:
            return

    def complete(self) -> None:
        self.advance(self.total, total=self.total)

    def _ensure_progress_and_task_id(self) -> tuple[Progress, TaskID] | None:
        progress = get_progress()
        assert progress, (
            f"expected progress to finish after task, but progress is None, task: {self.description}"
        )
        assert self._task_id is not None, (
            f"Task ID should not be None at this point: {self.description}"
        )
        task_removed = self._task_id not in progress.task_ids
        if task_removed:  # can happen if the ensure_progress_stopped decorator is used
            if not self.visible:  # doesn't matter, no change to output
                return None
            # Add it back to the progress to show it completed
            self._task_id = progress.add_task(
                description=self.description,
                start=False,
                total=self.total,
                completed=self._completed,  # type: ignore
                visible=self.visible,
                **(self.task_fields or {}),
            )

        return progress, self._task_id

    def advance(self, amount: float = 1.0, *, total: float | None = None) -> None:
        """
        total: In case the task has increased in size, this is the new total.
        Advance the task by a certain amount.
        For example 1 if total = 100
        Or 0.01 if total = 1
        """
        self._completed += amount
        progress_task_id = self._ensure_progress_and_task_id()
        if progress_task_id is None:
            return
        progress, task_id = progress_task_id
        progress.update(
            task_id,
            advance=amount,
            total=total,
            refresh=True,
        )
