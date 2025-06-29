import time

import pytest

from ask_shell.rich_live import add_renderable, get_live, live_frozen, render_live
from ask_shell.rich_progress import new_task


def test_live_frozen_task_when_frozen_dont_update_console(capture_console):
    live = get_live()
    assert not live.is_started
    with live_frozen():
        with new_task("Task 1", log_after_remove=False):
            assert not live.is_started
    assert not live.is_started
    assert "Task 1" not in capture_console.end_capture()


def test_live_frozen_while_task_updates_console_after(capture_console):
    live = get_live()
    assert not live.is_started
    with new_task("Task 1", log_after_remove=False, total=4) as task:
        assert live.is_started
        with live_frozen():
            task.update(advance=1)
            task.update(advance=1)
            assert not live.is_started
        assert live.is_started
    output = capture_console.end_capture()
    assert "25%" not in output
    assert "50%" in output
    assert "100%" in output


class _ErrorRenderable:
    def __init__(self) -> None:
        self.count = 0

    def __rich_console__(self, console, options):
        self.count += 1
        crash_trigger_count = 5
        if self.count == crash_trigger_count:
            raise ValueError("This is a test error")
        return [f"Crashing in {crash_trigger_count - self.count} more renders"]


def test_raising_an_error_in_renderable_does_have_a_deadlock(capture_console):
    # sourcery skip: no-loop-in-tests
    live = get_live()
    assert not live.is_started

    add_renderable(_ErrorRenderable(), order=1, name="error_renderable")
    with pytest.raises(ValueError, match="This is a test error"):
        for _ in range(10):
            assert live.is_started
            render_live()
    assert not live.is_started
    time.sleep(0.1)  # Allow the live to process the renderable
    output = capture_console.end_capture()
    assert "Crashing in 4 more renders" in output
