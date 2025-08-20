from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, TypeAlias, Union

from rich.console import Console
from zero_3rdparty.closable_queue import ClosableQueue

if TYPE_CHECKING:
    from ask_shell._internal.models import ShellRun


@dataclass
class ShellRunStdStarted:
    is_stdout: bool
    console: Console
    log_path: Path


@dataclass
class ShellRunStdOutput:
    is_stdout: bool
    content: str


@dataclass
class ShellRunPOpenStarted:
    p_open: subprocess.Popen


@dataclass
class ShellRunStdReadError:
    is_stdout: bool
    error: BaseException


@dataclass
class ShellRunRetryAttempt:
    attempt: int


@dataclass
class ShellRunBefore:
    run: ShellRun


@dataclass
class ShellRunAfter:
    run: ShellRun
    error: BaseException | None = None


OutputCallbackT: TypeAlias = Callable[
    [str], bool | None
]  # returns True if the callback is done and should be removed
ShellRunEventT: TypeAlias = Union[
    ShellRunBefore,
    ShellRunPOpenStarted,
    ShellRunStdStarted,
    ShellRunStdReadError,
    ShellRunStdOutput,
    ShellRunRetryAttempt,  # only on retries
    ShellRunAfter,
]
ShellRunCallbackT: TypeAlias = Callable[[ShellRunEventT], bool | None]
ShellRunQueueT: TypeAlias = ClosableQueue[ShellRunEventT]
