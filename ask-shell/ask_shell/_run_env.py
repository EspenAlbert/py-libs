import logging
import sys
from functools import lru_cache
from os import getenv

from zero_3rdparty.run_env import in_test_env, running_in_container_environment

from ask_shell._constants import ENV_PREFIX

ENV_NAME_FORCE_INTERACTIVE_SHELL = f"{ENV_PREFIX}FORCE_INTERACTIVE_SHELL"
logger = logging.getLogger(__name__)


@lru_cache
def interactive_shell() -> bool:
    if getenv(ENV_NAME_FORCE_INTERACTIVE_SHELL, "false").lower() in (
        "true",
        "1",
        "yes",
    ):
        logger.debug(
            f"Interactive shell forced by environment variable {ENV_NAME_FORCE_INTERACTIVE_SHELL}"
        )
        return True
    if non_interactive_reason := _not_interactive_reason():
        logger.debug(f"Interactive shell not available: {non_interactive_reason}")
        return False
    return True


def _not_interactive_reason() -> str:
    if in_test_env():
        return "Running in test environment"
    if getenv("TERM", "") in ("dumb", "unknown"):
        return "TERM environment variable is set to 'dumb' or 'unknown'"
    if not sys.stdout.isatty():
        return "Standard output is not a TTY"
    if getenv("CI", "false").lower() in ("true", "1", "yes"):
        return "Running in CI environment"
    if running_in_container_environment():
        return "Running in container environment"
    return ""
