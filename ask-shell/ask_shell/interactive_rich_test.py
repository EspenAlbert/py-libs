import logging

import pytest

from ask_shell.interactive_rich import (
    Progress,
    ensure_progress_stopped,
    get_progress,
    new_task,
)

logger = logging.getLogger(__name__)


def test_process_singleton():
    assert get_progress() is None
    progress = Progress()
    assert get_progress() is progress
    with pytest.raises(
        RuntimeError,
        match=r"Progress instance already created, multiple progresses not allowed. Use get_progress\(\) to access it",
    ):
        Progress()


def test_ensure_progress_stopped_no_progress_no_change():
    @ensure_progress_stopped
    def dummy_function():
        return "Function executed"

    assert dummy_function() == "Function executed"


def test_ensure_progress_stopped_with_progress_should_work_after_function_finishes(
    capsys,
):
    with Progress() as progress:

        @ensure_progress_stopped
        def dummy_function():
            assert not progress.live.is_started
            return "OK"

        assert dummy_function() == "OK"
        assert progress.live.is_started
        t1 = progress.add_task("Task 1", total=1)
        progress.update(t1, advance=1)
    out, _ = capsys.readouterr()
    assert "Task 1" in out
    assert "100%" in out


def test_ensure_progress_stopped_should_stop_should_remove_current_tasks(
    capture_console,
):
    with Progress(console=capture_console, auto_refresh=False) as progress:
        progress.add_task("Task 1", total=1)

        @ensure_progress_stopped
        def dummy_function():
            assert not progress.live.is_started
            return "OK"

        assert dummy_function() == "OK"
    out = capture_console.end_capture()
    assert "Task 1" in out
    assert "0%" in out


def test_task_should_raise_error_if_no_progress():
    with pytest.raises(
        RuntimeError,
        match=r"Progress instance not created\. Must have an active progress to enter a task\.",
    ):
        with new_task("Test Task"):
            pass


def test_task_should_create_and_finish_task(capsys):
    with Progress():
        with new_task("Test Task", total=5):
            logger.info("Doing something")
    stdout = capsys.readouterr().out
    assert "Test Task" in stdout
    assert "100%" in stdout


def test_stopped_should_still_complete(capsys):
    with Progress():
        with new_task("Test Task", total=5):

            @ensure_progress_stopped
            def dummy_function():
                logger.info("Doing something")
                return "OK"

            assert dummy_function() == "OK"
    stdout = capsys.readouterr().out
    assert "Test Task" in stdout
    assert "100%" in stdout


def test_task_should_update_progress(capture_console):
    with Progress(console=capture_console, auto_refresh=False):
        with new_task("Test Task", total=5) as task:
            for _ in range(5):
                task.advance(1)
    out = capture_console.end_capture()
    assert "Test Task" in out
    for i in range(1, 6):
        assert f"{20 * i}%" in out
