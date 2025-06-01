import sys
from functools import lru_cache
from os import getenv

from zero_3rdparty.run_env import in_test_env, running_in_container_environment

ENV_NAME_FORCE_INTERACTIVE_SHELL = "FORCE_INTERACTIVE_SHELL"


@lru_cache
def interactive_shell() -> bool:
    if getenv(ENV_NAME_FORCE_INTERACTIVE_SHELL, "false").lower() in (
        "true",
        "1",
        "yes",
    ):
        return True
    return (
        not running_in_container_environment()
        and not in_test_env()
        and sys.stdout.isatty()
        and getenv("CI", "false").lower() not in ("true", "1", "yes")
    )
