from functools import cached_property
from pathlib import Path
from pydoc import locate
from typing import Any, Callable, ClassVar

from model_lib.static_settings import StaticSettings
from pydantic import Field
from zero_3rdparty.file_utils import clean_dir
from zero_3rdparty.object_name import as_name


def default_callbacks_funcs() -> list[str]:
    from ask_shell.global_callbacks import (
        wait_on_available_threads,
    )

    return [
        as_name(call)
        for call in [
            wait_on_available_threads,
        ]
    ]


class AskShellSettings(StaticSettings):
    ENV_NAME_RUN_THREAD_COUNT: ClassVar[str] = "RUN_THREAD_COUNT"
    RUN_THREAD_COUNT_DEFAULT: ClassVar[int] = 50
    RUN_THREAD_COUNT: int = RUN_THREAD_COUNT_DEFAULT
    global_callback_strings: list[str] = Field(default_factory=default_callbacks_funcs)

    @cached_property
    def message_callbacks(
        self,
    ) -> list[Callable[[Any], bool]]:  # see models.MessageCallbackT
        return [locate(callback_str) for callback_str in self.global_callback_strings]  # type: ignore

    @property
    def run_logs(self) -> Path:
        return self.cache_root / "run_logs"

    def _last_run_counter(self) -> int:
        """Returns the next run counter based on existing directories."""
        run_logs = self.run_logs
        if not run_logs.exists():
            return 99
        existing_dirs = [path for path in run_logs.iterdir() if path.is_dir()]
        return min(
            (
                int(path.name.split("_")[0])
                for path in existing_dirs
                if path.name[0].isdigit()
            ),
            default=99,
        )

    def next_run_counter(self) -> int:
        from ask_shell.interactive2 import confirm

        last_counter = self._last_run_counter()
        if last_counter == 0:
            if confirm(f"Ok to clean the run logs directory: {self.run_logs}?"):
                clean_dir(self.run_logs, recreate=True)
                last_counter = 100
            else:
                raise ValueError(
                    f"Run logs directory {self.run_logs} is full! Please clean it up manually."
                )
        return last_counter - 1

    def next_run_logs_dir(self, exec_name: str) -> Path:
        """{XX}_{self.exec_name}"""
        next_counter = self.next_run_counter()
        return self.run_logs / f"{next_counter:02d}_{exec_name}"
