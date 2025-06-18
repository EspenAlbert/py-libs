from ask_shell.models import ShellConfig, ShellRun, ShellRunAfter, ShellRunStdOutput
from ask_shell.rich_live import get_live
from ask_shell.rich_run_state import _RunState


def test_run_with_output_is_logged_to_console(settings, capture_console, caplog):
    config = ShellConfig(
        shell_input='echo "Hello, World!"',
        print_prefix="Test Run",
        settings=settings,
    )
    run = ShellRun(config=config)
    state = _RunState()
    assert not get_live().is_started
    state.add_run(run)
    assert get_live().is_started
    assert state.active_runs == [run]
    assert state.no_user_input_runs
    run._on_event(
        ShellRunStdOutput(
            is_stdout=True,
            content="Hello, World!\n",
        ),
    )
    run._on_event(
        ShellRunStdOutput(
            is_stdout=False,
            content="This is an error message.\n",
        )
    )
    run._on_event(ShellRunAfter(run=run, error=Exception("Test error")))
    state.remove_run(run, error=Exception("Test error"))
    output = capture_console.end_capture()
    assert "Test Run" in output
    assert "Hello, World!" in output
    assert "This is an error message." in output
    assert "Test error" in output
    log_output = caplog.text
    assert "❌ 'echo \"Hello, World!\"'" in log_output
    assert not get_live().is_started
