from ask_shell._internal.models import (
    ShellRunAfter,
    ShellRunBefore,
)
from ask_shell._internal.rich_live import _live_is_frozen, get_live
from ask_shell._internal.rich_live_callback import (
    RunConsoleLogger,
)
from ask_shell.conftest import create_run_mocked_config


def test_live_frozen_when_user_input_task_is_running():
    console_logger = RunConsoleLogger()
    shell_run = create_run_mocked_config(user_input=True)
    console_logger(ShellRunBefore(run=shell_run))
    assert _live_is_frozen()
    assert not get_live().is_started
    console_logger(ShellRunAfter(run=shell_run))
    assert not _live_is_frozen()
