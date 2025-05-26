from __future__ import annotations

import os
import string
import subprocess
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path
from random import choices
from typing import Any, Callable, NamedTuple

from ask_shell.colors import ContentType
from ask_shell.printer import print_with

_empty = object()
string_or_digit = string.ascii_letters + string.digits
MAX_PREFIX_LEN = 30


def always_retry(_):
    return True


class StartResult(NamedTuple):
    p_open: subprocess.Popen
    stdout: list[str]
    stderr: list[str]


@dataclass
class BashConfig:
    """
    >>> BashConfig("some_script").print_prefix
    'some_script'
    >>> BashConfig("some_script some_arg").print_prefix
    'some_script some_arg'
    >>> BashConfig("some_script some_arg --option1").print_prefix
    'some_script some_arg'
    >>> BashConfig("some_script some_arg", cwd="/some/path/prefix").print_prefix
    'prefix some_script some_arg'
    >>> BashConfig("some_script some_arg", cwd="/some/path/prefix", print_prefix="override").print_prefix
    'override'
    """

    script: str
    env: dict[str, str] = _empty  # type: ignore
    cwd: str | Path = _empty  # type: ignore
    attempts: int = 1
    print_prefix: str = _empty  # type: ignore
    extra_popen_kwargs: dict = field(default_factory=dict)
    allow_non_zero_exit: bool = False
    should_retry: Callable[[BashRun], bool] = always_retry
    ansi_content: bool = False

    def __post_init__(self):
        if self.env is _empty:
            self.env = dict(**os.environ)
        if self.print_prefix is _empty:
            self._infer_print_prefix()

    def _infer_print_prefix(self):
        match self.script.split():
            case [program, arg, *_]:
                self.print_prefix = f"{program} {arg}"
            case [program]:
                self.print_prefix = program
            case _:
                self.print_prefix = "".join(choices(string_or_digit, k=5))
        if self.cwd is not _empty:
            self.print_prefix = f"{Path(self.cwd).name} {self.print_prefix}"
        self.print_prefix = self.print_prefix.strip()[:MAX_PREFIX_LEN]

    @property
    def popen_kwargs(self):
        kwargs: dict[str, Any] = {"env": self.env} | self.extra_popen_kwargs
        if self.cwd is not _empty:
            kwargs["cwd"] = self.cwd
        return kwargs


@dataclass
class BashRun:
    """Only created by this file never outside!"""

    config: BashConfig
    p_open: subprocess.Popen | None = field(init=False, default=None)

    _complete_flag: Future = field(default_factory=Future, init=False)
    _current_std_out: list[str] = field(init=False, default_factory=list)
    _current_std_err: list[str] = field(init=False, default_factory=list)

    def wait_until_complete(self, timeout: float | None = None):
        """Raises: BashError"""
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

    def _complete(self, error: BaseException | None = None):
        if self._complete_flag.done():
            print_with(
                "already done",
                prefix=self.config.print_prefix,
                content_type=ContentType.WARNING,
            )
            return
        if (
            (error or self.exit_code != 0)
            and self.config.allow_non_zero_exit
            or not error
            and self.exit_code == 0
        ):
            self._complete_flag.set_result(self)
        else:
            self._complete_flag.set_exception(BashError(self, error))

    def _set_start_result(self, start_result: StartResult):
        self.p_open = start_result.p_open
        self._current_std_out = start_result.stdout
        self._current_std_err = start_result.stderr

    @property
    def stdout(self) -> str:
        return "".join(self._current_std_out).strip("\n")

    @property
    def stderr(self) -> str:
        return "".join(self._current_std_err).strip("\n")

    @property
    def clean_complete(self):
        return self.exit_code == 0

    @property
    def is_running(self):
        return self.exit_code is None


class BashError(Exception):
    def __init__(self, run: BashRun, base_error: BaseException | None = None):
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


class RunIncompleteError(Exception):
    def __init__(self, run: BashRun):
        self.run = run
