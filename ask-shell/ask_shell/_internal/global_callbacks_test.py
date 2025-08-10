import logging
import os
import time
from unittest.mock import Mock

import pytest

from ask_shell._internal._run import (
    THREAD_POOL_FULL_WAIT_TIME_SECONDS,
    THREADS_PER_RUN,
    run,
    wait_on_ok_errors,
)
from ask_shell._internal.global_callbacks import wait_on_available_threads
from ask_shell._internal.models import ShellRun, ShellRunBefore
from ask_shell.settings import AskShellSettings

logger = logging.getLogger(__name__)


def test_wait_on_available_threads(settings):
    settings_args = settings.model_dump()
    settings_args.pop("global_callback_strings")
    settings = AskShellSettings(**settings_args)
    assert any(
        name.endswith(wait_on_available_threads.__name__)
        for name in settings.global_callback_strings
    )
    assert settings.message_callbacks
    assert wait_on_available_threads(ShellRunBefore(run=Mock(spec=ShellRun)))


@pytest.mark.skipif(os.environ.get("SLOW", "") == "", reason="needs os.environ[SLOW]")
def test_running_enough_scripts_to_wait(settings):
    settings.message_callbacks.append(wait_on_available_threads)
    count = (
        settings.thread_count // THREADS_PER_RUN + 2
    )  # at least 2 runs should be blocked
    before = time.monotonic()
    logger.info(f"start time: {before}")
    runs = [run(f"sleep 2 && echo {i}") for i in range(count)]  # will be blocked
    logger.info(f"started {len(runs)} runs, waiting for them to finish")
    ok, errors = wait_on_ok_errors(
        *runs, timeout=THREAD_POOL_FULL_WAIT_TIME_SECONDS * 2
    )
    after = time.monotonic()
    logger.info(f"end time: {after}")
    assert len(ok) == len(runs)
    assert not errors
    assert after - before > THREAD_POOL_FULL_WAIT_TIME_SECONDS
