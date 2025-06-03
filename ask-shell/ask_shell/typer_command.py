import logging
from functools import wraps
from typing import Callable, TypeVar

import typer
from rich.logging import RichHandler

from ask_shell.rich_live import get_live_console
from ask_shell.rich_progress import new_task
from ask_shell.settings import AskShellSettings

T = TypeVar("T", bound=Callable)


def track_progress(
    command: T,
) -> T:
    @wraps(command)
    def wrapper(*args, **kwargs):
        with new_task(
            description=f"Running command: '{command.__name__}'",
        ):
            return command(*args, **kwargs)

    return wrapper  # type: ignore


def configure_logging(
    app: typer.Typer,
    *,
    settings: AskShellSettings | None = None,
    app_pretty_exceptions_enable: bool = False,
    app_pretty_exceptions_show_locals: bool = False,
) -> logging.Handler:
    for command in app.registered_commands:
        command.callback = track_progress(command.callback)  # type: ignore
    settings = settings or AskShellSettings.from_env()
    handler = RichHandler(
        rich_tracebacks=False, level=settings.log_level, console=get_live_console()
    )
    logging.basicConfig(
        level=settings.log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[handler],
    )
    app.pretty_exceptions_enable = app_pretty_exceptions_enable
    app.pretty_exceptions_show_locals = app_pretty_exceptions_show_locals
    return handler
