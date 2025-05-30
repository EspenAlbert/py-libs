from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ask_shell.interactive_rich import Progress, get_progress
from ask_shell.models import (
    AfterRunMessage,
    BeforeRunMessage,
    InternalMessageT,
    POpenStartedMessage,
    RetryAttemptMessage,
    ShellRun,
    StdOutputMessage,
    StdReadErrorMessage,
    StdStartedMessage,
)


def _get_or_create_progress() -> Progress:
    progress = get_progress()
    if progress is None:
        return Progress(transient=True)
    return progress


def _deque_default() -> deque[str]:
    return deque(maxlen=30)


@dataclass
class _RunInfo:
    run: ShellRun
    stdout: deque[str] = field(default_factory=_deque_default)
    stderr: deque[str] = field(default_factory=_deque_default)

    log_path_stdout: Path | None = None
    log_path_stderr: Path | None = None

    error_read_stdout: BaseException | None = None
    error_read_stderr: BaseException | None = None
    started: bool = False
    attempt: int = 1

    @property
    def stdout_str(self) -> str:
        return "\n".join(self.stdout)

    @property
    def stderr_str(self) -> str:
        return "\n".join(self.stderr)

    def __call__(self, message: InternalMessageT) -> Any:
        match message:
            case StdOutputMessage(is_stdout=is_stdout, content=content):
                if is_stdout:
                    self.stdout.append(content)
                else:
                    self.stderr.append(content)
            case StdStartedMessage(is_stdout=is_stdout, log_path=log_path):
                if is_stdout:
                    self.log_path_stdout = log_path
                else:
                    self.log_path_stderr = log_path
            case POpenStartedMessage():
                self.started = True
            case RetryAttemptMessage(attempt=attempt):
                self.attempt = attempt
            case StdReadErrorMessage(is_stdout=is_stdout, error=error):
                if is_stdout:
                    self.error_read_stdout = error
                else:
                    self.error_read_stderr = error

    def __post_init__(self) -> None:
        self.run.config.message_callbacks.append(self)


class _SwitchCallbackError(Exception):
    def __init__(self, new_callback: _BaseCallback, active_progress: bool) -> None:
        self.new_callback = new_callback
        self.active_progress = active_progress


@dataclass
class _RunState:
    runs: dict[int, _RunInfo] = field(default_factory=dict)


@dataclass
class _BaseCallback:
    state: _RunState = field(default_factory=_RunState, init=False)

    def __call__(self, message: InternalMessageT) -> bool:
        match message:
            case BeforeRunMessage(run=run):
                run_id = id(run)
                if run_id in self.state.runs:
                    return False  # Run already exists, no need to add again
                self.state.runs[run_id] = _RunInfo(run=run)
            case AfterRunMessage(run=run):
                self.state.runs.pop(id(run), None)
            case StdStartedMessage(run=run, is_stdout=is_stdout):
                run_info = self.state.runs.get(id(run))
                assert run_info is not None, "Run info should exist for started run"
                if is_stdout:
                    run_info.log_path_stdout = run.log_path_stdout
                else:
                    run_info.log_path_stderr = run.log_path_stderr

        return False

    @property
    def runs(self) -> list[ShellRun]:
        return [info.run for info in self.state.runs.values()]


@dataclass
class _StdoutIsBusy(_BaseCallback):
    @property
    def no_user_input_runs(self) -> bool:
        return not any(run.config.user_input for run in self.runs)

    def __call__(self, message: InternalMessageT) -> bool:
        super().__call__(message)
        match message:
            case BeforeRunMessage(run=run):
                self.runs.append(run)
            case AfterRunMessage(run=run):
                self.runs.remove(run)
                if self.no_user_input_runs:
                    if not self.runs:
                        raise _SwitchCallbackError(_NoRuns(), active_progress=False)
                    raise _SwitchCallbackError(_StdoutIsFree(), active_progress=True)
        return False


@dataclass
class _StdoutIsFree(_BaseCallback):
    def __call__(self, message: InternalMessageT) -> bool:
        super().__call__(message)
        match message:
            case BeforeRunMessage(run=run) if run.config.user_input:
                raise _SwitchCallbackError(_StdoutIsBusy(), active_progress=False)
            case AfterRunMessage(run=run):
                if not self.runs:
                    raise _SwitchCallbackError(_NoRuns(), active_progress=False)
        return False


@dataclass
class _NoRuns(_BaseCallback):
    def __call__(self, message: InternalMessageT) -> bool:
        super().__call__(message)
        match message:
            case BeforeRunMessage(run=run):
                if run.config.user_input:
                    raise _SwitchCallbackError(_StdoutIsBusy(), active_progress=False)
                else:
                    raise _SwitchCallbackError(_StdoutIsFree(), active_progress=True)
        return False


@dataclass
class RunConsoleLogger:
    progress: Progress = field(default_factory=_get_or_create_progress)
    current_message_handler: _BaseCallback = field(init=False, default_factory=_NoRuns)

    @property
    def state(self) -> _RunState:
        return self.current_message_handler.state

    def __call__(self, message: InternalMessageT) -> bool:
        try:
            return self.current_message_handler(message)
        except _SwitchCallbackError as e:
            state = self.current_message_handler.state
            self.current_message_handler = e.new_callback
            self.current_message_handler.state = state
            if e.active_progress:
                self.progress.__enter__()
            else:
                self.progress.__exit__(None, None, None)
            return self(message)


_logger = RunConsoleLogger()


def callback(message: InternalMessageT) -> bool:
    return _logger(message)
