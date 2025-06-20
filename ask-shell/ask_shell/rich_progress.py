from __future__ import annotations

import logging
from dataclasses import dataclass, field
from threading import RLock
from typing import Callable, Self, TypeVar

from rich.progress import (
    BarColumn,
    Progress,
    Task,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from ask_shell.rich_live import RemoveLivePart, add_renderable, render_live
from ask_shell.settings import default_rich_info_style

logger = logging.getLogger(__name__)


def transient_progress() -> Progress:
    return Progress(
        TextColumn("%s{task.description}" % default_rich_info_style()),  # noqa: UP031 # a special template string for rich
        TaskProgressColumn(),
        BarColumn(),
        TimeElapsedColumn(),
        transient=True,
    )


def log_task_done(
    task: new_task,
    *,
    force_error: bool = False,
    error: BaseException | None = None,
    description_override: str | None = None,
    extra_parts: list[str] | None = None,
):
    exit_comji = "❌" if force_error or error is not None else "✅"
    description = description_override or task.description
    log_call = logger.info if exit_comji == "✅" else logger.error
    message_parts = [f"{exit_comji} {description}"]
    if rich_task := task._rich_task:
        if finish_time := rich_task.finished_time:
            message_parts.append(f"completed in {finish_time:.02f}s")
    if extra_parts := extra_parts or []:
        message_parts.append(" ".join(part for part in extra_parts if part))
    log_call(" ".join(message_parts))


def log_task_progress(task: new_task):
    logger.info(f"Progress: {task.description} - {task.progress_str}")


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

    def add_task(self, task: new_task) -> None:
        with self._lock:
            progress = self.get_progress()
            progress.tasks
            task._task_id = progress.add_task(
                description=task.description,
                total=task.total,
                visible=task.visible,
                **(task.task_fields or {}),
            )
            task._rich_task = next(t for t in progress.tasks if t.id == task._task_id)
            if len(progress.tasks) == 1:
                self._remove_progress = add_renderable(
                    progress, name=self.title, order=-100
                )

    def remove_task(self, task: new_task, error: BaseException | None = None) -> None:
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
            if task.log_after_remove:
                log_task_done(task, error=error)
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
        log_update: bool = False,
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
            if log_update:
                log_task_progress(task)


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
    log_after_remove: bool = True  # Adds a log message when the task is removed. Useful for tracking task completion.
    log_updates: bool = False  # Adds a log message every time update is called. Useful if you are doing an interactive loop, to show progress updates.
    manager: ProgressManager = field(default_factory=get_default_progress_manager)

    _task_id: TaskID | None = field(init=False, default=None)
    _rich_task: Task | None = field(init=False, default=None)
    completed: float = field(init=False, default=0.0)

    @property
    def is_finished(self) -> bool:
        return self.completed >= self.total

    @property
    def progress_str(self) -> str:
        return f"{self.completed / self.total:.0%}"

    def __post_init__(self):
        assert self.total > 0, "Total must be greater than 0"

    def __enter__(self) -> Self:
        self.manager.add_task(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.complete()  # Ensure we mark it as complete
        self.manager.remove_task(self, error=exc_val)

    def complete(self) -> None:
        self.update(advance=self.total, total=self.total, log_update=False)

    def update(
        self,
        *,
        advance: float | None = None,
        total: float | None = None,
        log_update: bool | None = None,
        **task_fields,
    ) -> None:
        """
        total: In case the task has increased in size, this is the new total.
        Advance the task by a certain amount.
        For example 1 if total = 100
        Or 0.01 if total = 1
        """
        if advance is not None:
            self.completed += advance
            self.completed = min(self.completed, self.total)
        if total is not None:
            self.total = total
        if log_update is None:
            log_update = self.log_updates
        self.manager.update_task(
            self, advance=advance, total=total, log_update=log_update, **task_fields
        )
