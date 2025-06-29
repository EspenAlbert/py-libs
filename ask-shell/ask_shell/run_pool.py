import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from math import ceil
from threading import Event, RLock
from typing import Any, Callable, Protocol, TypeVar

from ask_shell._run import (
    THREADS_PER_RUN,
    get_pool,
    handle_interrupt_wait,
    max_run_count_for_workers,
    wait_if_many_runs,
)
from ask_shell.rich_progress import new_task
from ask_shell.settings import AskShellSettings

T_co = TypeVar("T_co", covariant=True)


class SubmitFunc(Protocol[T_co]):
    def __call__(self, *args: Any, **kwds: Any) -> T_co: ...


@dataclass
class run_pool:
    task_name: str
    total: int = 0
    max_concurrent_submits: int = field(default=4)
    threads_used_per_submit: int = (
        THREADS_PER_RUN + 1
    )  # If you are using `run` or `run_and_wait` this should be `THREADS_PER_RUN` + extra threads for your own tasks
    sleep_time: float = 1
    sleep_callback: Callable[[], Any] | None = None
    exit_wait_timeout: float | None = (
        None  # If set, will wait for the pool to finish before exiting the context manager
    )

    pool: ThreadPoolExecutor = field(init=False, default_factory=get_pool)
    _pool_max_workers: int = field(init=False)
    _max_run_count_with_this_pool: int = field(init=False)
    _lock: RLock = field(init=False, default_factory=RLock)
    _current_submit_count: int = field(init=False, default=0)
    _task: new_task | None = field(init=False, default=None)
    _event: Event = field(init=False, default_factory=Event)

    def __post_init__(self):
        self.pool_max_workers = self.pool._max_workers
        max_run_count = max_run_count_for_workers(self.pool_max_workers)
        workers_required_if_full = (
            self.max_concurrent_submits * self.threads_used_per_submit
        )
        run_count_used_by_this_pool = ceil(workers_required_if_full // THREADS_PER_RUN)
        assert run_count_used_by_this_pool < max_run_count, (
            f"Run count used by this pool ({run_count_used_by_this_pool}) exceeds max run count ({max_run_count}). Adjust {AskShellSettings.ENV_NAME_RUN_THREAD_COUNT} environment variable or decrease `max_concurrent_submits` parameter."
        )
        self._max_run_count_with_this_pool = max_run_count - run_count_used_by_this_pool

    def __enter__(self):
        self._task = new_task(self.task_name, self.total)
        self._task.__enter__()
        return self

    def _on_submit_done(self):
        """Callback to be called when a submit is done. This is used to decrement the current submit count."""
        with self._lock:
            self._current_submit_count -= 1
            if task := self._task:
                task.update(advance=1)
            if self._current_submit_count == 0:
                self._event.set()

    def submit(self, fn: SubmitFunc[T_co], /, *args, **kwargs) -> Future[T_co]:
        """Submit a task to the pool. Might block if the pool is full."""

        # problem: There is a bit of lag from submit until the run is actually started,
        with self._lock:
            self._current_submit_count += 1
            if self._current_submit_count == 1:
                self._event = Event()  # reset the event when the first submit is made
        with handle_interrupt_wait(
            interrupt_message=f"run_pool submit for {self.task_name}"
        ):
            while self._current_submit_count >= self.max_concurrent_submits:
                if self.sleep_callback:
                    self.sleep_callback()
                time.sleep(self.sleep_time)
        # in case more runs are already submitted
        wait_if_many_runs(
            max_run_count=self._max_run_count_with_this_pool,
            sleep_time=self.sleep_time,
            sleep_callback=self.sleep_callback,
        )
        future = self.pool.submit(fn, *args, **kwargs)
        future.add_done_callback(lambda _: self._on_submit_done())
        return future

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        # no cleanup necessary, the pool will be cleaned up automatically due to atexit call
        with handle_interrupt_wait(
            interrupt_message=f"interrupt in `run_pool` exit method for {self.task_name}"
        ):
            self._event.wait(self.exit_wait_timeout)

        if task := self._task:
            task.__exit__(exc_type, exc_value, traceback)
