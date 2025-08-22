import logging
import os
from datetime import datetime, timedelta
from functools import cached_property, lru_cache
from pathlib import Path
from pydoc import locate
from threading import RLock
from typing import Any, Callable, ClassVar, Literal, Self

from model_lib.static_settings import StaticSettings
from pydantic import ConfigDict, Field, model_validator
from zero_3rdparty.datetime_utils import utc_now
from zero_3rdparty.file_utils import clean_dir
from zero_3rdparty.object_name import as_name

logger = logging.getLogger(__name__)

DEFAULT_RUN_LOGS_BASE_DIR = "run_logs"


def default_callbacks_funcs() -> list[str]:
    from ask_shell._internal.global_callbacks import (
        wait_on_available_threads,
    )
    from ask_shell._internal.rich_live_callback import rich_live_callback

    return [
        as_name(call)
        for call in [
            wait_on_available_threads,
            rich_live_callback,
        ]
    ]


def default_remove_os_secrets() -> bool:
    from ask_shell._internal._run_env import interactive_shell

    return not interactive_shell


ENV_PREFIX = "ASK_SHELL_"


@lru_cache  # to avoid cleaning run logs multiple times
def _clean_run_logs(run_logs: Path, clean_value: str) -> None:
    if not run_logs.exists():
        return
    if run_logs.name != DEFAULT_RUN_LOGS_BASE_DIR:
        from ask_shell._internal.interactive import confirm  # Avoid circular import

        if confirm(
            f"Run logs directory '{run_logs}' is not the default {DEFAULT_RUN_LOGS_BASE_DIR}. Do you want to skip cleaning?",
            default=True,
        ):
            return

    if clean_value == "yesterday":
        clean_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        clean_date = clean_value
    try:
        parsed_date = datetime.strptime(clean_date, "%Y-%m-%d")
    except ValueError:
        logger.warning(
            "Invalid date format for run logs cleaning. Expected 'YYYY-MM-DD' or 'yesterday'."
        )
        return
    for path in run_logs.iterdir():
        if not path.is_dir():
            continue
        dir_name = path.name
        try:
            dir_date = datetime.strptime(dir_name, "%Y-%m-%d")
        except ValueError:
            continue
        if dir_date < parsed_date:
            logger.info(f"Cleaning run logs directory: {path}")
            clean_dir(path, recreate=False)


_rlock = RLock()


class AskShellSettings(StaticSettings):
    model_config = ConfigDict(populate_by_name=True)  # type: ignore
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "UNSET"] = (
        "UNSET"
    )

    ENV_NAME_FORCE_INTERACTIVE_SHELL: ClassVar[str] = (
        f"{ENV_PREFIX}FORCE_INTERACTIVE_SHELL"
    )
    force_interactive_shell: bool = Field(
        default=False,
        alias=ENV_NAME_FORCE_INTERACTIVE_SHELL,
        description="Useful for testing",
    )
    ENV_NAME_THREAD_COUNT: ClassVar[str] = f"{ENV_PREFIX}THREAD_COUNT"
    thread_count: int = Field(
        default=50,
        alias=ENV_NAME_THREAD_COUNT,
        description="Thread count for ask-shell pool",
    )
    thread_pool_full_wait_time_seconds: float = Field(
        default=5,
        alias=f"{ENV_PREFIX}THREAD_POOL_FULL_WAIT_TIME_SECONDS",
        description="How long to wait when the thread pools is full before trying again",
    )
    search_enabled_after_choices: int = Field(
        default=7,
        alias=f"{ENV_PREFIX}SEARCH_ENABLED_AFTER_CHOICES",
        description="How many choices to show before enabling search",
    )
    global_callback_strings: list[str] = Field(
        default_factory=default_callbacks_funcs,
        alias=f"{ENV_PREFIX}GLOBAL_CALLBACKS",
        description="Use global callbacks to receive ShellRun events. Uses `locate` to find the callback function by its string name. Setting this will override defaults",
    )
    remove_os_secrets: bool = Field(
        default_factory=default_remove_os_secrets,
        alias=f"{ENV_PREFIX}REMOVE_OS_SECRETS",
        description="Use a log filter to remove secrets from the terminal output. No guarantees though. Always be careful when logging.",
    )
    run_logs_dir: Path | None = Field(
        default=None,
        description="Directory to store run logs. If not set, defaults to `cache_root/run_logs/YYYY-MM-DD`. You can also use `configure_run_logs_dir_if_unset` to set it dynamically.",
        alias=f"{ENV_PREFIX}RUN_LOGS_DIR",
    )
    run_logs_clean: str = Field(
        default="yesterday",
        description="Runs once If `run_logs_dir` is not set. Can be 'yesterday' or a date string like '2023-01-01'. Will clean all logs up until the specified date but not that date itself.",
        alias=f"{ENV_PREFIX}RUN_LOGS_CLEAN",
    )

    @model_validator(mode="after")
    def ensure_vars_set(self) -> Self:
        if self.log_level == "UNSET":
            self.log_level = "INFO"  # Default log level, might be subject to change
        if self.run_logs_dir is None and (clean_value := self.run_logs_clean):
            _clean_run_logs(self.run_logs.parent, clean_value)
        return self

    @cached_property
    def message_callbacks(
        self,
    ) -> list[Callable[[Any], bool]]:  # see models.MessageCallbackT
        return [locate(callback_str) for callback_str in self.global_callback_strings]  # type: ignore

    @property
    def run_logs(self) -> Path:
        if self.run_logs_dir is not None:
            self.run_logs_dir.mkdir(parents=True, exist_ok=True)
            return self.run_logs_dir
        return (
            self.cache_root
            / DEFAULT_RUN_LOGS_BASE_DIR
            / datetime.now().strftime("%Y-%m-%d")
        )

    def configure_run_logs_dir_if_unset(
        self,
        *,
        new_absolute_path: Path | None = None,
        new_relative_path: str = "",
        skip_env_update: bool = False,
        date_folder_expressing: str | None = "%Y-%m-%dT%H-%M-%S",
    ) -> Path:
        from ask_shell._internal._run_env import interactive_shell

        if self.run_logs_dir is not None:
            return self.run_logs_dir
        assert new_relative_path or new_absolute_path, (
            "Either new_absolute_path or new_relative_path must be provided"
        )
        if new_absolute_path is not None:
            self.run_logs_dir = new_absolute_path
        else:
            self.run_logs_dir = self.cache_root / new_relative_path
        if date_folder_expressing:
            if interactive_shell():
                dt_folder = datetime.now().strftime(date_folder_expressing)
            else:
                dt_folder = f"{utc_now().strftime(date_folder_expressing)}Z"
            self.run_logs_dir = self.run_logs_dir / dt_folder
        self.run_logs_dir.mkdir(parents=True, exist_ok=True)
        if not skip_env_update:
            os.environ["RUN_LOGS_DIR"] = str(
                self.run_logs_dir
            )  # ensures default settings creation will have the RUN_LOGS_DIR set
        return self.run_logs_dir

    def _last_run_counter(self) -> int:
        """Returns the next run counter based on existing directories."""
        run_logs = self.run_logs
        if not run_logs.exists():
            return 0
        existing_dirs = [path for path in run_logs.iterdir() if path.is_dir()]
        return max(
            (
                int(path.name.split("_")[0])
                for path in existing_dirs
                if path.name[0].isdigit()
            ),
            default=0,
        )

    def next_run_counter(self) -> int:
        last_counter = self._last_run_counter()
        return last_counter + 1

    def next_run_logs_dir(self, exec_name: str) -> Path:
        """{XX}_{self.exec_name}"""
        with _rlock:
            next_counter = self.next_run_counter()
            new_dir = self.run_logs / f"{next_counter:03d}_{exec_name}"
            new_dir.mkdir(parents=True, exist_ok=True)
            return new_dir


def default_rich_info_style() -> str:
    return "[cyan]"


_global_settings = AskShellSettings.for_testing(
    global_callback_strings=[], remove_os_secrets=False
)
