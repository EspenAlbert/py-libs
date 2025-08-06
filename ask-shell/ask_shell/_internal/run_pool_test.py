import logging
import os
import time

import pytest

from ask_shell._internal._run import max_run_count_for_workers, run_and_wait
from ask_shell._internal.run_pool import run_pool

logger = logging.getLogger(__name__)


@pytest.mark.skipif(os.environ.get("SLOW", "") == "", reason="needs os.environ[SLOW]")
def test_running_enough_scripts_to_wait(settings, capture_console):
    submit_tasks = max_run_count_for_workers(settings.RUN_THREAD_COUNT)

    submit_task_sleep_time = 1

    def run_sleep_command(i: int) -> str:
        result = run_and_wait(f"sleep {submit_task_sleep_time} && echo {i}")
        return result.stdout_one_line

    log_calls = 0

    def log_sleeping():
        nonlocal log_calls
        log_calls += 1
        logger.info(
            f"Waiting for threads to finish before starting new tasks, sleeping call {log_calls}"
        )

    with run_pool(
        task_name="Test Submit should block",
        total=10,
        sleep_time=0.1,
        sleep_callback=log_sleeping,
    ) as pool:
        start_time = time.monotonic()
        runs = [
            pool.submit(run_sleep_command, i) for i in range(submit_tasks)
        ]  # should block since some thread counts are reserved for the `run_pool`
        assert time.monotonic() - start_time > submit_task_sleep_time, (
            "Should have waited for some tasks to finish before starting new ones"
        )
        results = [future.result() for future in runs]
        assert len(results) == submit_tasks, "All tasks should have completed"
    output = capture_console.end_capture()
    assert "Test Submit should block" in output, "Task name should be in the output"


def test_run_pool_multiple_usages(capture_console):
    with run_pool(task_name="First Pool", total=5) as pool1:
        for i in range(5):
            pool1.submit(lambda x: x, i)

    with run_pool(task_name="Second Pool", total=3) as pool2:
        for i in range(3):
            pool2.submit(lambda x: x, i)

    output = capture_console.end_capture()
    assert "First Pool" in output, "First pool task name should be in the output"
    assert "Second Pool" in output, "Second pool task name should be in the output"
