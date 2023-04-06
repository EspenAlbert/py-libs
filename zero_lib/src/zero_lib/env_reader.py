from __future__ import annotations

from os import getenv
from typing import Iterable, TypeVar

from zero_lib.run_env import in_test_env
from zero_lib.str_utils import want_bool

ENV_LOG_MAX_MSG_LENGTH = "log_max_msg_length"
ENV_THREAD_POOL_MAX_WORKERS = "thread_pool_max_workers"
ENV_PROCESS_SHUTDOWN_TIMEOUT = "process_shutdown_timeout"
ENV_POOL_STATE_CHECK_INTERVAL = "pool_state_check_interval"
ENV_LOG_FORMAT_CONSOLE = "log_format_console"


def upper_lower_case(env_key: str) -> Iterable[str]:
    yield env_key
    yield env_key.lower()
    yield env_key.upper()


T = TypeVar("T")


def read_env_value(env_key: str, default: T) -> T:
    value_converter = type(default)
    if value_converter is bool:
        value_converter = want_bool
    for key_variation in upper_lower_case(env_key):
        if str_value := getenv(key_variation, None):
            return value_converter(str_value)
    return default


def log_max_msg_length(default=1000) -> int:
    return read_env_value(ENV_LOG_MAX_MSG_LENGTH, default)


def thread_pool_workers(default=100) -> int:
    """
    >>> thread_pool_workers(10)
    10
    >>> thread_pool_workers()
    100
    """
    return read_env_value(ENV_THREAD_POOL_MAX_WORKERS, default)


def process_shutdown_timeout(default=10) -> float:
    return read_env_value(ENV_PROCESS_SHUTDOWN_TIMEOUT, default)


def pool_state_check_interval(default=0.25, default_in_test=0.01) -> float:
    default = default_in_test if in_test_env() else default
    return read_env_value(ENV_POOL_STATE_CHECK_INTERVAL, default)


def log_format_console(
    default: str = "%(asctime)s.%(msecs)03d %(levelname)-7s %(threadName)-s %(name)-s %(lineno)-s %(message)-s",
) -> str:
    return read_env_value(ENV_LOG_FORMAT_CONSOLE, default)
