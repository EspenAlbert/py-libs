from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.progress import Progress

from ask_shell.models import (
    InternalMessageT,
    POpenStartedMessage,
    RetryAttemptMessage,
    ShellRun,
    StdOutputMessage,
    StdReadErrorMessage,
    StdStartedMessage,
)


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


@dataclass
class _RunState:
    runs: dict[int, _RunInfo] = field(default_factory=dict)
    _progress: Progress | None = None

    @property
    def progress(self) -> Progress:
        if self._progress is None:
            self._progress = Progress()
        return self._progress

    def __rich_console__(self, console, options):
        raise NotImplementedError
