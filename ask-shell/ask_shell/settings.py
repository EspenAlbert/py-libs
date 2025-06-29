import logging
import os
from datetime import datetime, timedelta
from functools import cached_property, lru_cache
from pathlib import Path
from pydoc import locate
from typing import Any, Callable, ClassVar, Literal, Self

from model_lib.static_settings import StaticSettings
from pydantic import Field, model_validator
from zero_3rdparty.datetime_utils import utc_now
from zero_3rdparty.file_utils import clean_dir
from zero_3rdparty.object_name import as_name

from ask_shell._constants import ENV_PREFIX
from ask_shell._run_env import interactive_shell

logger = logging.getLogger(__name__)

DEFAULT_RUN_LOGS_BASE_DIR = "run_logs"


def default_callbacks_funcs() -> list[str]:
    from ask_shell.global_callbacks import (
        wait_on_available_threads,
    )
    from ask_shell.rich_live_callback import rich_live_callback

    return [
        as_name(call)
        for call in [
            wait_on_available_threads,
            rich_live_callback,
        ]
    ]


class AskShellSettings(StaticSettings):
    ENV_NAME_RUN_THREAD_COUNT: ClassVar[str] = f"{ENV_PREFIX}RUN_THREAD_COUNT"
    RUN_THREAD_COUNT_DEFAULT: ClassVar[int] = 50
    ENV_NAME_THREAD_POOL_FULL_WAIT_TIME_SECONDS: ClassVar[str] = (
        f"{ENV_PREFIX}THREAD_POOL_FULL_WAIT_TIME_SECONDS"  # How long to wait when the thread pools is full before trying again
    )
    THREAD_POOL_FULL_WAIT_TIME_SECONDS_DEFAULT: ClassVar[int] = 5
    ENV_NAME_SEARCH_ENABLED_AFTER_CHOICES: ClassVar[str] = (
        f"{ENV_PREFIX}SEARCH_ENABLED_AFTER_CHOICES"  # How many choices to show before enabling search
    )
    SEARCH_ENABLED_AFTER_CHOICES_DEFAULT: ClassVar[int] = 7
    RUN_THREAD_COUNT: int = RUN_THREAD_COUNT_DEFAULT

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "UNSET"] = (
        "UNSET"
    )

    # These should be prefixed with `ENV_PREFIX` to avoid conflicts with other libraries
    global_callback_strings: list[str] = Field(default_factory=default_callbacks_funcs)
    remove_os_secrets: bool = Field(default_factory=lambda: not interactive_shell())
    run_logs_dir: Path | None = Field(
        default=None,
        description="Directory to store run logs. If not set, defaults to `cache_root/run_logs/YYYY-MM-DD`. You can also use `configure_run_logs_dir_if_unset` to set it dynamically.",
    )
    run_logs_clean: str = Field(
        default="yesterday",
        description="Runs once If `run_logs_dir` is not set. Can be 'yesterday' or a date string like '2023-01-01'. Will clean all logs up until the specified date but not that date itself.",
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
        next_counter = self.next_run_counter()
        return self.run_logs / f"{next_counter:03d}_{exec_name}"


def default_rich_info_style() -> str:
    return "[cyan]"


@lru_cache  # to avoid cleaning run logs multiple times
def _clean_run_logs(run_logs: Path, clean_value: str) -> None:
    if not run_logs.exists():
        return
    if run_logs.name != DEFAULT_RUN_LOGS_BASE_DIR:
        from ask_shell.interactive import confirm  # Avoid circular import

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
