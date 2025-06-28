import logging

from ask_shell._run import (
    current_run_count,
    max_run_count_for_workers,
    wait_if_many_runs,
)
from ask_shell.models import ShellRunBefore, ShellRunEventT

logger = logging.getLogger(__name__)


def wait_on_available_threads(message: ShellRunEventT) -> bool:
    """This callback avoids starting a new run when the thread pool is almost full. We don't want to start a new run unless we have enough threads see `THREADS_PER_RUN`."""
    if isinstance(message, ShellRunBefore):
        max_count = max_run_count_for_workers() - 1  # have some margin for other tasks

        def log_wait():
            logger.warning(
                f"Run count={current_run_count()} exceeds max {max_count}. "
                f"Waiting for threads to finish before starting {message.run}..."
            )

        wait_if_many_runs(max_count, sleep_callback=log_wait)
    return True  # Always remove the callback after run has started
