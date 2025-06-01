from dataclasses import dataclass
from unittest.mock import Mock

import pytest

from ask_shell.interactive_rich import Progress
from ask_shell.models import (
    AfterRunMessage,
    BeforeRunMessage,
    InternalMessageT,
    ShellConfig,
    ShellRun,
    StdOutputMessage,
)
from ask_shell.rich_live_callback import (
    RunConsoleLogger,
    _NoRuns,
    _StdoutIsBusy,
    _StdoutIsFree,
)
from ask_shell.rich_live_state import _RunInfo


def run(user_input: bool = False) -> ShellRun:
    return ShellRun(
        config=Mock(spec=ShellConfig, message_callbacks=[], user_input=user_input)
    )


@dataclass
class _MessageTestStep:
    message: InternalMessageT
    expected_callback: type
    expected_stdout: str = ""
    expected_stderr: str = ""

    @property
    def expected_callback_name(self) -> str:
        return self.expected_callback.__name__


@dataclass
class _MessageTestCase:
    name: str
    steps: list[_MessageTestStep]
    run: ShellRun


run_no_user_input = run(user_input=False)
run_with_user_input = run(user_input=True)
_test_cases = [
    _MessageTestCase(
        name="One 1st run should switch to _StdoutIsBusy when user_input is True",
        steps=[
            _MessageTestStep(
                message=BeforeRunMessage(run=run_with_user_input),
                expected_callback=_StdoutIsBusy,
            ),
            _MessageTestStep(
                message=AfterRunMessage(run=run_with_user_input),
                expected_callback=_NoRuns,
            ),
        ],
        run=run_with_user_input,
    ),
    _MessageTestCase(
        name="One 1st run should switch to _StdoutIsFree when user_input is False and switch back to _NoRuns after run",
        run=run_no_user_input,
        steps=[
            _MessageTestStep(
                message=BeforeRunMessage(run=run_no_user_input),
                expected_callback=_StdoutIsFree,
            ),
            _MessageTestStep(
                message=StdOutputMessage(is_stdout=True, content="Test output"),
                expected_callback=_StdoutIsFree,
                expected_stdout="Test output",
            ),
            _MessageTestStep(
                message=StdOutputMessage(is_stdout=False, content="Test stderr"),
                expected_callback=_StdoutIsFree,
                expected_stderr="Test stderr",
            ),
            _MessageTestStep(
                message=AfterRunMessage(run=run_no_user_input),
                expected_callback=_NoRuns,
            ),
        ],
    ),
]


@pytest.mark.parametrize("tc", _test_cases, ids=[tc.name for tc in _test_cases])
def test_run_console_logger(tc: _MessageTestCase, capture_console):
    console_logger = RunConsoleLogger(
        progress=Progress(console=capture_console, auto_refresh=False)
    )

    for step in tc.steps:
        message = step.message
        assert not console_logger(message)
        if isinstance(message, StdOutputMessage):
            tc.run._on_message(message)
        assert (
            type(console_logger.current_message_handler).__name__
            == step.expected_callback_name
        )
        if stdout := step.expected_stdout:
            run_info: _RunInfo = console_logger.state.runs[id(tc.run)]
            assert run_info.stdout_str == stdout
        if stderr := step.expected_stderr:
            run_info: _RunInfo = console_logger.state.runs[id(tc.run)]
            assert run_info.stderr_str == stderr
    assert not console_logger.state.runs, f"Runs should be empty after test: {tc.name}"
