import logging
import os
import sys
import traceback
from contextlib import suppress
from functools import wraps
from pathlib import Path
from types import TracebackType
from typing import Callable, TypeVar

import click
import typer
from rich.logging import RichHandler
from rich.traceback import Traceback

import ask_shell
from ask_shell.rich_live import get_live_console, log_to_live
from ask_shell.rich_progress import new_task
from ask_shell.settings import AskShellSettings, default_rich_info_style

T = TypeVar("T", bound=Callable)
original_excepthook = sys.excepthook


def track_progress_decorator(
    *,
    settings: AskShellSettings,
    skip_except_hook: bool = False,
    use_app_name_command_for_logs: bool = True,
    app_name: str,
    command_name: str,
) -> Callable[[T], T]:
    def decorator(command: T) -> T:
        @wraps(command)
        def wrapper(*args, **kwargs):
            if not skip_except_hook:  # this must be done inside of the call as the typer.main sets the except hook when the app is called
                sys.excepthook = except_hook  # type: ignore
            if use_app_name_command_for_logs:
                settings.configure_run_logs_dir_if_unset(
                    new_relative_path=f"{app_name}/{command_name}"
                )
            sys_args = " ".join(sys.argv)
            with new_task(
                description=f"Running: '{sys_args}'",
            ):
                try:
                    return command(*args, **kwargs)
                except BaseException as e:
                    raise e  # re-raise the exception to be handled by the except hook
                finally:
                    log_exit_summary(settings)

        return wrapper  # type: ignore

    return decorator


def log_exit_summary(settings: AskShellSettings):
    log_to_live(
        f"{default_rich_info_style()}You can find the run logs in {settings.run_logs} "
    )


def configure_logging(
    app: typer.Typer,
    *,
    settings: AskShellSettings | None = None,
    app_pretty_exceptions_enable: bool = False,
    app_pretty_exceptions_show_locals: bool = False,
    skip_except_hook: bool = False,
    use_app_name_command_for_logs: bool = True,
) -> logging.Handler:
    settings = settings or AskShellSettings.from_env()
    app_name = app.info.name or "typer_app"
    for command in app.registered_commands:
        command.callback = track_progress_decorator(
            skip_except_hook=skip_except_hook,
            settings=settings,
            use_app_name_command_for_logs=use_app_name_command_for_logs,
            app_name=app_name,
            command_name=command.name or command.callback.__name__,  # type: ignore
        )(
            command.callback  # type: ignore
        )
    handler = RichHandler(
        rich_tracebacks=False, level=settings.log_level, console=get_live_console()
    )
    logging.basicConfig(
        level=settings.log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[handler],
    )
    if settings.remove_os_secrets:
        hide_secrets(handler, {**os.environ})
    app.pretty_exceptions_enable = app_pretty_exceptions_enable
    app.pretty_exceptions_show_locals = app_pretty_exceptions_show_locals
    return handler


def except_hook(
    exc_type: type[BaseException], exc_value: BaseException, tb: TracebackType | None
) -> None:
    """Similar to typer's except hook"""
    internal_modules = [typer, click, ask_shell]
    console = get_live_console()
    rich_tb = Traceback.from_exception(
        exc_type,
        exc_value,
        tb,
        show_locals=True,
        suppress=internal_modules,
        width=console.width,
    )
    console.print(rich_tb)
    standard_exception = traceback.TracebackException(
        exc_type, exc_value, tb, limit=-7, compact=True
    )
    for line in standard_exception.format(chain=True):
        console.print(line, end="")


def remove_secrets(message: str, secrets: list[str]) -> str:
    for secret in secrets:
        message = message.replace(secret, "***")
    return message


class SecretsHider(logging.Filter):
    def __init__(self, secrets: list[str], name: str = "") -> None:
        self.secrets = secrets
        super().__init__(name)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = remove_secrets(record.msg, self.secrets)
        return True


dangerous_keys = ["key", "token", "secret"]
safe_keys: list[str] = ["/"]


def hide_secrets(handler: logging.Handler, secrets_dict: dict[str, str]) -> None:
    secrets_to_hide = set()
    for key, value in secrets_dict.items():
        if not isinstance(value, str):
            continue
        key_lower = key.lower()
        if (
            key_lower in {"true", "false"}
            or value.lower() in {"true", "false"}
            or value.isdigit()
        ):
            continue
        with suppress(Exception):
            if Path(value).exists():
                continue
        if any(safe in key_lower for safe in safe_keys):
            continue
        if any(danger_key_part in key_lower for danger_key_part in dangerous_keys):
            secrets_to_hide.add(value)
    if not secrets_to_hide:
        return
    handler.addFilter(SecretsHider(list(secrets_to_hide), name="secrets-hider"))
