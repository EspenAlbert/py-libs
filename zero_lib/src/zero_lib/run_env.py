import logging
import os
import subprocess
import sys
import tempfile
from functools import lru_cache
from io import TextIOWrapper
from os import getenv
from pathlib import Path
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def running_in_container_environment() -> bool:
    if os.path.isfile("/.dockerenv"):
        return True
    with tempfile.NamedTemporaryFile() as tmp:
        stderr = TextIOWrapper(tmp)
        try:
            output = subprocess.check_output(
                ["ps -eZ --no-headers | grep containerd"], shell=True, stderr=stderr
            )
            return bool(output)
        except subprocess.CalledProcessError:
            return False


@lru_cache(maxsize=1)
def running_in_pants():
    return bool(getenv("RUNNING_IN_PANTS"))


def running_on_host():
    return not any([running_in_container_environment(), running_in_pants()])


T = TypeVar("T")


def on_host_in_container(on_host_value: T, in_container_value: T) -> Callable[[], T]:
    def inner():
        if running_on_host():
            return on_host_value
        return in_container_value

    return inner


@lru_cache(maxsize=1)
def in_test_env() -> bool:
    return "pytest" in Path(sys.argv[0]).name
