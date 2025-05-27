from __future__ import annotations

import os
import platform
import string
import subprocess
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path
from shutil import which
from typing import Any, Callable, NamedTuple, Self

from model_lib.model_base import Entity
from pydantic import Field, model_validator

from ask_shell.colors import ContentType
from ask_shell.printer import print_with

_empty = object()
string_or_digit = string.ascii_letters + string.digits
MAX_PREFIX_LEN = 30


def always_retry(_):
    return True


def install_instructions(binary_name: str) -> str:
    return (
        f"Please install '{binary_name}' using your package manager or download it from "
        f"https://www.google.com/search?q=install+{binary_name}+{platform.system()}"
    )


class StartResult(NamedTuple):
    p_open: subprocess.Popen
    stdout: list[str]
    stderr: list[str]


def is_executable(filepath: Path) -> bool:
    return filepath.is_file() and os.access(filepath, os.X_OK)


class ShellInput(NamedTuple):
    binary_name: str
    file_path: Path | None
    args: list[str]

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
    skip_os_env: bool = False
    skip_binary_check: bool = False
    cwd: Path = Field(default=None, description="Set to Path.cwd() if not provided")  # type: ignore
    attempts: int = 1
    print_prefix: str = Field(
        default=None, description="Use cwd+binary_name+first_arg if not provided"
    )  # type: ignore
    extra_popen_kwargs: dict = Field(default_factory=dict)
    allow_non_zero_exit: bool = False
    should_retry: Callable[[ShellRun], bool] = always_retry
    ansi_content: bool = Field(default=None, description="Inferred if not provided")  # type: ignore
    is_binary_call: bool = Field(default=None, description="Inferred if not provided")  # type: ignore

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
        return kwargs


@dataclass
class ShellRun:
    """Only created by this file never outside!"""

    config: ShellConfig
    p_open: subprocess.Popen | None = field(init=False, default=None)

    _complete_flag: Future = field(default_factory=Future, init=False)
    _current_std_out: list[str] = field(init=False, default_factory=list)
    _current_std_err: list[str] = field(init=False, default_factory=list)

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
            self._complete_flag.set_exception(ShellError(self, error))

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


class RunIncompleteError(Exception):
    def __init__(self, run: ShellRun):
        self.run = run
