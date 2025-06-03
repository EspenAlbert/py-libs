from ask_shell.rich_live import get_live, live_frozen
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
