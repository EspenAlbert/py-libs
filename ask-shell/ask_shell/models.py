from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
from concurrent.futures import Future
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from shutil import which
from threading import RLock
from typing import Any, Callable, NamedTuple, Self, TypeAlias, Union

from model_lib.model_base import Entity
from model_lib.serialize.parse import parse_payload
from pydantic import Field, model_validator
from rich.console import Console
from zero_3rdparty.closable_queue import ClosableQueue

from ask_shell._run_env import interactive_shell
from ask_shell.settings import AskShellSettings

logger = logging.getLogger(__name__)
ERROR_MESSAGE_INTERACTIVE_SHELL = "Interactive shell is required for user input, but the current shell is not interactive, you can use skip_interactive_check=True to avoid this error"


def always_retry(_):
    return True


def install_instructions(binary_name: str) -> str:
    return (
        f"Please install '{binary_name}' using your package manager or download it from "
        f"https://www.google.com/search?q=install+{binary_name}+{platform.system()}"
    )


def is_executable(filepath: Path) -> bool:
    return filepath.is_file() and os.access(filepath, os.X_OK)


class ShellInput(NamedTuple):
    binary_name: str
    file_path: Path | None
    args: list[str]

    @property
    def name(self) -> str:
        if self.file_path:
            return self.file_path.name
        return self.binary_name

    @property
    def is_binary_call(self) -> bool:
        return self.binary_name != ""

    def file_path_relative(self, cwd: Path) -> str:
        assert self.file_path, "file_path should not be None"
        return (
            str(self.file_path.relative_to(cwd))
            if self.file_path.is_relative_to(cwd)
            else str(self.file_path)
        )

    @property
    def first_arg(self) -> str:
        for i, arg in enumerate(self.args):
            if arg.startswith("-"):
                continue
            if i == 0:
                return arg
            prev_arg = self.args[i - 1]
            prev_arg_is_flag = prev_arg.startswith("-") and "=" not in prev_arg
            if not prev_arg_is_flag:
                return arg
        return ""


@dataclass
class StdStartedMessage:
    is_stdout: bool
    console: Console
    log_path: Path


@dataclass
class StdOutputMessage:
    is_stdout: bool
    content: str


@dataclass
class POpenStartedMessage:
    p_open: subprocess.Popen


@dataclass
class StdReadErrorMessage:
    is_stdout: bool
    error: BaseException


@dataclass
class RetryAttemptMessage:
    attempt: int


@dataclass
class BeforeRunMessage:
    run: ShellRun


@dataclass
class AfterRunMessage:
    run: ShellRun
    error: BaseException | None = None


OutputCallbackT: TypeAlias = Callable[
    [str], bool | None
]  # returns True if the callback is done and should be removed
InternalMessageT: TypeAlias = Union[
    BeforeRunMessage,
    POpenStartedMessage,
    StdStartedMessage,
    StdReadErrorMessage,
    StdOutputMessage,
    RetryAttemptMessage,  # only on retries
    AfterRunMessage,
]
MessageCallbackT: TypeAlias = Callable[[InternalMessageT], bool | None]
ShellRunQueueT: TypeAlias = ClosableQueue[InternalMessageT]


class ShellConfig(Entity):
    """
    >>> ShellConfig("some_script").print_prefix
    'some_script'
    >>> ShellConfig("some_script some_arg").print_prefix
    'some_script some_arg'
    >>> ShellConfig("some_script some_arg --option1").print_prefix
    'some_script some_arg'
    >>> ShellConfig("some_script some_arg", cwd="/some/path/prefix").print_prefix
    'prefix some_script some_arg'
    >>> ShellConfig("some_script some_arg", cwd="/some/path/prefix", print_prefix="override").print_prefix
    'override'
    """

    shell_input: str
    env: dict[str, str] = Field(default_factory=dict)
    extra_popen_kwargs: dict = Field(default_factory=dict)
    allow_non_zero_exit: bool = False
    skip_os_env: bool = False
    skip_binary_check: bool = False
    include_log_time: bool = False
    skip_interactive_check: bool = (
        False  # can be useful for testing purposes, to skip the interactive shell check
    )
    cwd: Path = Field(default=None, description="Set to Path.cwd() if not provided")  # type: ignore
    user_input: bool = False

    attempts: int = 1
    print_prefix: str = Field(
        default=None, description="Use cwd+binary_name+first_arg if not provided"
    )  # type: ignore
    should_retry: Callable[[ShellRun], bool] = always_retry
    ansi_content: bool = Field(default=None, description="Inferred if not provided")  # type: ignore
    is_binary_call: bool = Field(default=None, description="Inferred if not provided")  # type: ignore
    settings: AskShellSettings = field(default_factory=AskShellSettings.from_env)
    run_output_dir: Path | None = Field(
        default=None,
        description="Directory to store run logs, defaults to settings.run_logs /{XX}_{self.exec_name}",
    )
    run_log_stem_prefix: str = Field(default="", description="Prefix for run log stem")
    skip_html_log_files: bool = Field(
        default=False,
        description="Skip HTML log files, by default dumps HTML logs to support viewing colored output in browsers",
    )
    message_callbacks: list[MessageCallbackT] = Field(
        default_factory=list,
        description="Callbacks for run messages, useful for custom handling of stdout/stderr",
    )
    terminal_width: int | None = 999

    @property
    def exec_name(self) -> str:
        return self.binary_file_args.name

    def run_log_stem(self, attempt: int) -> str:
        if attempt > 1:
            return f"{self.exec_name}_{attempt}"
        return self.exec_name

    def run_output_dir_resolved(self) -> Path:
        if self.run_output_dir is None:
            return self.settings.next_run_logs_dir(self.exec_name)
        return self.run_output_dir

    @property
    def binary_file_args(self) -> ShellInput:
        match self.shell_input.split():
            case [file_or_binary, *args] if os.sep in file_or_binary:
                file_or_binary_path = Path(file_or_binary).resolve()
                if is_executable(file_or_binary_path):
                    return ShellInput("", file_or_binary_path, args)
                return ShellInput(file_or_binary, None, args)
            case [file_or_binary, *args]:
                return ShellInput(file_or_binary, None, args)
            case _:
                raise ValueError("shell_input must not be empty")

    @model_validator(mode="after")
    def post_init(self) -> Self:
        if self.cwd is None:
            self.cwd = Path.cwd().resolve()
        parsed_input = self.binary_file_args
        if (
            not self.skip_binary_check
            and parsed_input.is_binary_call
            and not which(parsed_input.binary_name)
        ):
            install = install_instructions(parsed_input.binary_name)
            raise ValueError(
                f"Binary or non-executable '{parsed_input.binary_name}' not found. {install}"
            )
        if self.is_binary_call is None:
            self.is_binary_call = parsed_input.is_binary_call
        if self.print_prefix is None:
            self._infer_print_prefix(parsed_input)
        if not self.skip_os_env:
            self.env = os.environ | self.env
        if self.ansi_content is None:
            self._infer_ansi_content(parsed_input)
        if self.user_input and self.include_log_time is None:
            self.include_log_time = False
        if self.user_input and not self.skip_interactive_check:
            assert interactive_shell(), ERROR_MESSAGE_INTERACTIVE_SHELL
        self.message_callbacks.extend(self.settings.message_callbacks)
        return self

    def _infer_print_prefix(self, parsed_input: ShellInput):
        cwd = self.cwd
        prefix_parts = [f"{cwd.parent.name}/{cwd.name}" if cwd.parents else cwd.name]
        if parsed_input.is_binary_call:
            prefix_parts.append(parsed_input.binary_name)
        else:
            prefix_parts.append(parsed_input.file_path_relative(cwd))
        if first_arg := parsed_input.first_arg:
            prefix_parts.append(first_arg)
        self.print_prefix = " ".join(prefix_parts)

    def _infer_ansi_content(self, parsed_input: ShellInput):
        if parsed_input.is_binary_call and parsed_input.binary_name in (
            "terraform",
            "kubectl",
        ):
            self.ansi_content = True
        else:
            self.ansi_content = False

    @property
    def popen_kwargs(self):
        kwargs: dict[str, Any] = {"env": self.env} | self.extra_popen_kwargs
        kwargs["cwd"] = self.cwd
        if self.user_input:
            kwargs["stdin"] = sys.stdin
        return kwargs


@dataclass
class ShellRun:
    """Stores dynamic behavior. Only created by this file never outside.

    Args:
        _start_flag: Future[ShellRun]: Flag that is set when the run has both p_open and stdout/stderr reading started. During multiple attempts, only the 1st attempt will call it.

    """

    config: ShellConfig
    p_open: subprocess.Popen | None = field(init=False, default=None)

    _start_flag: Future[ShellRun] = field(default_factory=Future, init=False)
    _complete_flag: Future[ShellRun] = field(default_factory=Future, init=False)
    _stdout: Console | None = field(init=False, default=None)
    _stdout_log_path: Path | None = field(init=False, default=None)
    _stderr: Console | None = field(init=False, default=None)
    _stderr_log_path: Path | None = field(init=False, default=None)
    _queue: ShellRunQueueT = field(init=False, default_factory=ClosableQueue)
    _lock: RLock = field(init=False, default_factory=RLock)
    _current_attempt: int = field(init=False, default=1)

    @property
    def has_started(self) -> bool:
        return self._stdout is not None and self._stderr is not None

    def __str__(self) -> str:
        return " ".join(
            part
            for part in (
                "ShellRun(",
                self.config.print_prefix,
                "running" if self.is_running else f"exit_code={self.exit_code}",
                (
                    ""
                    if self._current_attempt == 1
                    else f"attempt={self._current_attempt}/{self.config.attempts}"
                ),
                ")",
            )
            if part
        )

    def add_output_callback(
        self, call: OutputCallbackT, *, is_stdout: bool, skip_old_lines: bool = False
    ) -> Callable[[], None] | None:
        """Adds a callback that will be called on each new line of output.
        Args:
            call: Callable that takes a line of output and returns True if the callback is done and should be removed.
            is_stdout: If True, the callback will be called on stdout, otherwise on stderr.
            skip_old_lines: If True, the callback will not be called on old lines of output, only new ones.

        Returns:
            Callable[[], None]: A function that can be called to remove the callback. None, if the callback is already removed.

        Warning:
            When `skip_old_lines` is True, the initial lines of stdout/stderr might have a "[08:34:09]" or similar prefix.
            Also, there is a chance the same line will be called twice

        """

        def only_on_output_callback(message: InternalMessageT) -> bool | None:
            if isinstance(message, StdOutputMessage) and message.is_stdout == is_stdout:
                return call(message.content)
            return False

        def remove_callback():
            with self._lock:
                with suppress(ValueError):  # if the callback was already removed
                    self.config.message_callbacks.remove(only_on_output_callback)

        with self._lock:
            self.config.message_callbacks.append(only_on_output_callback)
        if skip_old_lines:
            return remove_callback
        start_lines = (
            self.stdout.splitlines() if is_stdout else self.stderr.splitlines()
        )
        for line in start_lines:
            if call(line):
                remove_callback()
                return None
        return remove_callback

    def _on_message(self, message: InternalMessageT):
        with self._lock:
            for callback in list(self.config.message_callbacks):
                if callback(message):  # todo: call safely?
                    self.config.message_callbacks.remove(callback)
            match message:
                case StdStartedMessage(
                    is_stdout=True, console=console, log_path=log_path
                ):
                    self._stdout = console
                    self._stdout_log_path = log_path
                case StdStartedMessage(
                    is_stdout=False, console=console, log_path=log_path
                ):
                    self._stderr = console
                    self._stderr_log_path = log_path
                case POpenStartedMessage(p_open=p_open):
                    self.p_open = p_open
                case RetryAttemptMessage(attempt=attempt):
                    if not self.config.skip_html_log_files:
                        self._dump_html_logs()
                    self._reset_read_state(attempt)
            if not self._start_flag.done() and self.has_started:
                self._start_flag.set_result(self)

    def wait_on_started(self, timeout: float | None = None) -> ShellRun:
        return self._start_flag.result(timeout)

    def wait_until_complete(self, timeout: float | None = None):
        """Raises: ShellError"""
        self._complete_flag.result(timeout)

    def add_done_callback(self, call: Callable[[], Any]):
        def inner(_):
            call()

        if not self.is_running:
            raise ValueError("script is already done")
        self._complete_flag.add_done_callback(inner)

    @property
    def exit_code(self) -> int | None:
        if p_open := self.p_open:
            return p_open.returncode
        return None

    def _complete(
        self, error: BaseException | None = None, queue_consumer: Future | None = None
    ):
        with self._lock:
            if self._complete_flag.done():
                logger.warning(f"already done {self}")
                return
            self._queue.close()
        if queue_consumer:  # wait outside of lock, since the callback use the lock
            queue_consumer.result()  # ensure the queue consumer is done before calling complete
        with self._lock:
            if (
                (error or self.exit_code != 0)
                and self.config.allow_non_zero_exit
                or not error
                and self.exit_code == 0
            ):
                self._complete_flag.set_result(self)
            else:
                shell_error = ShellError(self, error)
                if (
                    not self._start_flag.done()
                ):  # if the run has not started yet, we must also set the start flag
                    self._start_flag.set_exception(shell_error)
                self._complete_flag.set_exception(shell_error)

    @property
    def stdout(self) -> str:
        if self._stdout_log_path is None:
            return ""
        return self._stdout_log_path.read_text().strip()

    def stdout_json(self) -> dict | list | str | None:
        all_stdout = "".join(self.stdout.splitlines())
        return parse_payload(all_stdout, "json") if all_stdout else None

    @property
    def stderr(self) -> str:
        if self._stderr_log_path is None:
            return ""
        return self._stderr_log_path.read_text().strip()

    @property
    def clean_complete(self):
        return self.exit_code == 0

    @property
    def is_running(self):
        return not self._complete_flag.done()

    def _dump_html_logs(self):
        if (stdout_logs := self._stdout_log_path) and self._stdout:
            stdout_logs_html = stdout_logs.with_suffix(".html")
            stdout_logs_html.write_text(self._stdout.export_html(clear=False))
        if (stderr_logs := self._stderr_log_path) and self._stderr:
            stderr_logs_html = stderr_logs.with_suffix(".html")
            stderr_logs_html.write_text(self._stderr.export_html(clear=False))

    def _reset_read_state(self, attempt: int):
        self._current_attempt = attempt
        self._stdout = None
        self._stderr = None
        self.p_open = None
        self._stdout_log_path = None
        self._stderr_log_path = None


class ShellError(Exception):
    def __init__(self, run: ShellRun, base_error: BaseException | None = None):
        self.run = run
        self.base_error = base_error

    @property
    def exit_code(self):
        return self.run.exit_code

    @property
    def stdout(self):
        return self.run.stdout

    @property
    def stderr(self):
        return self.run.stderr

    def __str__(self) -> str:
        lines_stdout, lines_stderr = (
            self.stdout.splitlines()[-10:],
            self.stderr.splitlines()[-10:],
        )
        if lines_stdout:
            lines_stdout.insert(0, "STDOUT")
        if lines_stderr:
            lines_stderr.insert(0, "STDERR")
        last_lines_str = "\n".join(
            line.strip() for line in lines_stdout + lines_stderr if line.strip()
        )
        return f"{str(self.run)}\nExit code: {self.exit_code}\nlines:{last_lines_str}"


class RunIncompleteError(Exception):
    def __init__(self, run: ShellRun):
        self.run = run
