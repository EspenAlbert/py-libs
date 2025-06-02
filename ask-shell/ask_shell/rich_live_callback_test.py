from ask_shell.conftest import create_run_mocked_config
from ask_shell.models import (
    AfterRunMessage,
    BeforeRunMessage,
)
from ask_shell.rich_live import _live_is_frozen, get_live
from ask_shell.rich_live_callback import (
    RunConsoleLogger,
)


def test_live_frozen_when_user_input_task_is_running(capture_console):
    console_logger = RunConsoleLogger()
    shell_run = create_run_mocked_config(user_input=True)
    console_logger(BeforeRunMessage(run=shell_run))
    assert _live_is_frozen()
    assert not get_live().is_started
    console_logger(AfterRunMessage(run=shell_run))
    assert not _live_is_frozen()
