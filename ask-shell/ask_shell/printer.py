from __future__ import annotations

import typing
from collections import ChainMap
from contextlib import contextmanager
from random import randint
from typing import Any, Protocol

from rich.console import Console
from rich.text import Text

from ask_shell.colors import EXTRA_COLORS, ContentType

_DEFAULT_CONTENT_TYPE = ContentType.DEFAULT


class PrintWith(Protocol):
    def __call__(
        self,
        content: str,
        *,
        prefix: str,
        content_type: str = _DEFAULT_CONTENT_TYPE,
        ansi_content: bool = False,
    ) -> Any:
        pass


def _default_print_with(
    content: str,
    *,
    prefix: str,
    content_type: str = _DEFAULT_CONTENT_TYPE,
    ansi_content: bool = False,
):
    color_prefix = get_color(prefix)
    if ansi_content:
        ansi_text = Text.from_ansi(content)
        if colored_prefix := with_color(color_prefix, prefix):
            print(f"{colored_prefix}", ansi_text)
        else:
            print(ansi_text)
        return
    color_content = get_color(content_type)
    content_colored = with_color(color_content, content.rstrip())
    if colored_prefix := with_color(color_prefix, prefix):
        print(f"{colored_prefix} {content_colored}")
    else:
        print(content_colored)


_print_with = _default_print_with


def print_with(
    content: str,
    *,
    prefix: str,
    content_type: str = _DEFAULT_CONTENT_TYPE,
    ansi_content: bool = False,
):
    return _print_with(
        content, prefix=prefix, content_type=content_type, ansi_content=ansi_content
    )


@contextmanager
def print_with_override(new_call: PrintWith, call_old: bool = True):
    global _print_with
    old = _print_with
    if call_old:

        def call(*args, **kwargs):
            old(*args, **kwargs)
            return new_call(*args, **kwargs)

    else:
        call = new_call
    _print_with = call
    try:
        yield
    finally:
        _print_with = old


console = Console(
    log_time=True, width=240, log_path=False, no_color=False, force_terminal=True
)


def print(*args, **kwargs):
    console.log(*args, **kwargs)


def log_exception(error):
    console.print_exception()


_PREFIX_COLOR = {"": ""}
_COLORS: typing.ChainMap = ChainMap(ContentType.colors(), _PREFIX_COLOR)


def get_color(key: str) -> str:
    global _PREFIX_COLOR
    if key in _COLORS:  # empty value might still be valid
        return _COLORS[key]
    # https://rich.readthedocs.io/en/stable/appendix/colors.html
    options = EXTRA_COLORS - set(_COLORS.values())
    if len(options) < len(EXTRA_COLORS) // 2:
        _PREFIX_COLOR.clear()
        _PREFIX_COLOR[""] = ""
        options = EXTRA_COLORS
    options = list(options)  # type: ignore
    color = options[randint(0, len(options) - 1)]  # type: ignore
    _PREFIX_COLOR[key] = color
    return color


def with_color(color: str, content: str):
    if not color:
        return content
    return f"[{color}]{content}[/]"
