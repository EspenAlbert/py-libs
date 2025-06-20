import logging
import time

import ask_shell._run
from ask_shell.models import ShellRunBefore, ShellRunEventT

logger = logging.getLogger(__name__)


def wait_on_available_threads(message: ShellRunEventT) -> bool:
    if isinstance(message, ShellRunBefore):
        max_workers = ask_shell._run.get_pool()._max_workers
        max_count = max_workers // ask_shell._run.THREADS_PER_RUN - 1
        while ask_shell._run.current_run_count() > max_count:
            logger.warning(
                f"Run count={ask_shell._run.current_run_count()} exceeds max {max_count}. "
                f"Waiting for threads to finish before starting {message.run}..."
            )
            time.sleep(ask_shell._run.THREAD_POOL_FULL_WAIT_TIME_SECONDS)
    return True  # always remove the callback from the run, BeforeRunMessage should be the first message
