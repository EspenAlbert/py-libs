import logging
import os
from contextlib import contextmanager
from typing import ContextManager, Mapping

logger = logging.getLogger(__name__)


class os_env_temp:
    def __init__(self, name: str, value: str):
        self.name = name
        self.value = value

    def __enter__(self):
        self.maybe_previous = os.environ.get(self.name)
        if not isinstance(self.value, str):
            logger.warning(
                f"env_var={self.name}, {self.value} is not str, converting str({self.value})"
            )
            self.value = str(self.value)
        os.environ[self.name] = self.value

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.maybe_previous:
            os.environ[self.name] = self.maybe_previous
        else:
            del os.environ[self.name]

    @classmethod
    def from_dict(cls, d: Mapping) -> ContextManager:
        os_env_temps = [cls(key, value) for key, value in d.items()]

        @contextmanager
        def inner():
            for temp in os_env_temps:
                temp.__enter__()
            try:
                logger.info(f"loading env_vars from dict: {list(d.keys())}")
                yield
            finally:
                logger.info("restoring env vars")
                for temp in os_env_temps:
                    temp.__exit__(None, None, None)

        return inner()
