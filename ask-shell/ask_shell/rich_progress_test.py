import logging

from ask_shell.rich_live import get_live, pause_live
from ask_shell.rich_progress import (
    get_progress,
    new_task,
)

logger = logging.getLogger(__name__)


def test_process_singleton():
    assert get_progress() is not None


def test_pause_live_no_progress_no_change():
    @pause_live
    def dummy_function():
        return "Function executed"

    assert dummy_function() == "Function executed"


def test_pause_live_should_still_complete_task(
    capture_console,
):
    with new_task("Task 1", total=1):
        live = get_live()
        assert live.is_started

        @pause_live
        def dummy_function():
            assert not live.is_started
            return "OK"

        assert dummy_function() == "OK"
    out = capture_console.end_capture()
    assert "Task 1" in out
    assert "0%" in out
    assert "100%" in out
    assert not get_progress().tasks
    assert not get_live().is_started
    with new_task("Task 2", total=1):
        assert get_live().is_started


def test_task_should_create_and_finish_task(capture_console):
    with new_task("Test Task", total=5):
        logger.info("Doing something")
    stdout = capture_console.end_capture()
    assert "Test Task" in stdout
    assert "100%" in stdout


def test_task_should_update_progress(capture_console):
    with new_task("Test Task", total=5) as task:
        for _ in range(5):
            task.advance(1)
    out = capture_console.end_capture()
    assert "Test Task" in out
    for i in range(1, 6):
        assert f"{20 * i}%" in out
