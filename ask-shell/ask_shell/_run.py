"""Design Principles:
1. ShellConfig used to provide user configuration of the run.
2. A ShellRun is created for each run, which manages the execution and output.
3. The events are communicated through a queue, guaranteeing the order of messages.
4. You can either run or run_and_wait, where the latter waits for completion while the 1st will exit after command has started.
5. Message Callbacks can be used to direct output to the console, by default it is directed to a `.log` file which supports dumping ANSI content at the end of the run to a `.html` file.
6. Retries are supported, with a configurable number of attempts and a retry condition.
7. Any errors are converted into a `ShellError` which contains the run and base exception. Use `allow_non_zero_exit` to allow runs to complete with a non-zero exit code without raising this error.
"""

from __future__ import annotations

import atexit
import logging
import os
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import suppress
from dataclasses import dataclass
from os import getenv, setsid
from pathlib import Path
from typing import IO, Any, Callable

from model_lib.pydantic_utils import copy_and_validate
from rich.ansi import AnsiDecoder
from rich.console import Console
from rich.errors import MarkupError

from ask_shell.models import (
    RunIncompleteError,
    ShellConfig,
    ShellRun,
    ShellRunAfter,
    ShellRunBefore,
    ShellRunEventT,
    ShellRunPOpenStarted,
    ShellRunQueueT,
    ShellRunRetryAttempt,
    ShellRunStdOutput,
    ShellRunStdReadError,
    ShellRunStdStarted,
)
from ask_shell.settings import AskShellSettings

logger = logging.getLogger(__name__)
THREADS_PER_RUN = 4  # Each run will take 4 threads: 1 for stdout, 1 for stderr, 1 for consuming queue messages and 1 for popen wait.
THREAD_POOL_FULL_WAIT_TIME_SECONDS = float(
    getenv(
        AskShellSettings.ENV_NAME_THREAD_POOL_FULL_WAIT_TIME_SECONDS,
        AskShellSettings.THREAD_POOL_FULL_WAIT_TIME_SECONDS_DEFAULT,
    )
)

_pool = ThreadPoolExecutor(
    max_workers=int(
        getenv(
            AskShellSettings.ENV_NAME_RUN_THREAD_COUNT,
            AskShellSettings.RUN_THREAD_COUNT_DEFAULT,
        )
    )
)


def get_pool() -> ThreadPoolExecutor:
    """Get the thread pool executor used for running shell commands."""
    return _pool


_runs: dict[
    int, ShellRun
] = {}  # internal to store running ShellRuns to support stopping them on exit


def current_run_count() -> int:
    return len(_runs)


def wait_if_many_runs(
    max_run_count: int,
    *,
    sleep_time: float = THREAD_POOL_FULL_WAIT_TIME_SECONDS,
    sleep_callback: Callable[[], None] | None = None,
):
    with handle_interrupt_wait(
        interrupt_message="interrupt when waiting for runs to finish",
        immediate_kill=False,
    ):
        while current_run_count() > max_run_count:
            if sleep_callback:
                sleep_callback()
            time.sleep(sleep_time)


def max_run_count_for_workers(worker_count: int | None = None) -> int:
    """Calculate the maximum number of runs that can be executed concurrently based on the number of workers."""
    if worker_count is None:
        worker_count = _pool._max_workers  # type: ignore
    return max(1, worker_count // THREADS_PER_RUN)  # leave some threads for other tasks


def stop_runs_and_pool(reason: str = "atexit", immediate: bool = False):
    if _runs:
        logger.warning("STOPPING stop_runs_and_pool")
        kill_all_runs(reason=reason, immediate=immediate)

    _pool.shutdown(wait=True)


atexit.register(stop_runs_and_pool)


def run(
    config: ShellConfig | str,
    *,
    allow_non_zero_exit: bool | None = None,
    ansi_content: bool | None = None,
    attempts: int | None = None,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    extra_popen_kwargs: dict | None = None,
    is_binary_call: bool | None = None,
    message_callbacks: list[Callable[[ShellRunEventT], bool]] | None = None,
    print_prefix: str | None = None,
    run_log_stem_prefix: str | None = None,
    run_output_dir: Path | None | None = None,
    settings: AskShellSettings | None = None,
    should_retry: Callable[[ShellRun], bool] | None = None,
    skip_binary_check: bool | None = None,
    skip_html_log_files: bool | None = None,
    skip_progress_output: bool | None = None,
    include_log_time: bool | None = None,
    skip_os_env: bool | None = None,
    start_timeout: float | None = None,
    terminal_width: int | None = None,
    skip_interactive_check: bool | None = None,
) -> ShellRun:
    config = _as_config(
        config,
        allow_non_zero_exit=allow_non_zero_exit,
        ansi_content=ansi_content,
        attempts=attempts,
        cwd=cwd,
        env=env,
        extra_popen_kwargs=extra_popen_kwargs,
        is_binary_call=is_binary_call,
        message_callbacks=message_callbacks,
        print_prefix=print_prefix,
        run_log_stem_prefix=run_log_stem_prefix,
        run_output_dir=run_output_dir,
        settings=settings,
        should_retry=should_retry,
        skip_binary_check=skip_binary_check,
        skip_html_log_files=skip_html_log_files,
        skip_progress_output=skip_progress_output,
        include_log_time=include_log_time,
        skip_os_env=skip_os_env,
        terminal_width=terminal_width,
        skip_interactive_check=skip_interactive_check,
    )
    assert not config.user_input, (
        "run() does not support user_input (only 1 should be active at a time), use run_and_wait() instead"
    )
    run = ShellRun(config)
    _pool.submit(_execute_run, run)
    with handle_interrupt_wait(f"interrupt when starting {run}"):
        return run.wait_on_started(start_timeout)


def run_and_wait(
    script: ShellConfig | str,
    timeout: float | None = None,
    *,
    allow_non_zero_exit: bool | None = None,
    ansi_content: bool | None = None,
    attempts: int | None = None,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    extra_popen_kwargs: dict | None = None,
    is_binary_call: bool | None = None,
    message_callbacks: list[Callable[[ShellRunEventT], bool]] | None = None,
    print_prefix: str | None = None,
    run_log_stem_prefix: str | None = None,
    run_output_dir: Path | None | None = None,
    settings: AskShellSettings | None = None,
    should_retry: Callable[[ShellRun], bool] | None = None,
    skip_binary_check: bool | None = None,
    skip_progress_output: bool | None = None,
    skip_html_log_files: bool | None = None,
    include_log_time: bool | None = None,
    skip_os_env: bool | None = None,
    user_input: bool | None = None,
    terminal_width: int | None = None,
    skip_interactive_check: bool | None = None,
) -> ShellRun:
    config = _as_config(
        script,
        allow_non_zero_exit=allow_non_zero_exit,
        ansi_content=ansi_content,
        attempts=attempts,
        cwd=cwd,
        env=env,
        extra_popen_kwargs=extra_popen_kwargs,
        is_binary_call=is_binary_call,
        message_callbacks=message_callbacks,
        print_prefix=print_prefix,
        run_log_stem_prefix=run_log_stem_prefix,
        run_output_dir=run_output_dir,
        settings=settings,
        should_retry=should_retry,
        skip_binary_check=skip_binary_check,
        skip_html_log_files=skip_html_log_files,
        include_log_time=include_log_time,
        skip_os_env=skip_os_env,
        user_input=user_input,
        terminal_width=terminal_width,
        skip_interactive_check=skip_interactive_check,
        skip_progress_output=skip_progress_output,
    )
    run = ShellRun(config)
    _pool.submit(_execute_run, run)
    with handle_interrupt_wait(f"interrupt when waiting for {run}"):
        run.wait_until_complete(timeout)
    return run


@dataclass
class handle_interrupt_wait:
    interrupt_message: str
    immediate_kill: bool = False

    def __enter__(self):
        """Context manager to ensure that all runs are stopped on exit."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Handle exit by stopping all runs."""
        if exc_type is KeyboardInterrupt or exc_type is InterruptedError:
            interrupt_error = f"{self.interrupt_message} {exc_value!r}"
            stop_runs_and_pool(interrupt_error, immediate=self.immediate_kill)


def _as_config(config: ShellConfig | str, **kwargs) -> ShellConfig:
    kwargs_not_none = {k: v for k, v in kwargs.items() if v is not None}
    if isinstance(config, str):
        return ShellConfig(shell_input=config, **kwargs_not_none)
    assert isinstance(config, ShellConfig), f"not a ShellConfig or str: {config!r}"
    return copy_and_validate(config, **kwargs_not_none)


def run_error(run: ShellRun, timeout: float | None = 1) -> BaseException | None:
    try:
        run._complete_flag.result(timeout=timeout)
    except BaseException as e:
        return e


def wait_on_ok_errors(
    *runs: ShellRun,  # type: ignore
    timeout: float | None = None,
    skip_kill_timeouts: bool = False,  # type: ignore
) -> tuple[list[ShellRun], list[tuple[BaseException, ShellRun]]]:
    future_runs = {run._complete_flag: run for run in runs}
    with handle_interrupt_wait("interrupt when waiting for runs"):
        done, not_done = wait(
            [run._complete_flag for run in runs], timeout, return_when="ALL_COMPLETED"
        )
    errors: list[tuple[BaseException, ShellRun]] = []
    oks: list[ShellRun] = []

    if not_done:
        if skip_kill_timeouts:
            errors.extend(
                (RunIncompleteError(future_runs[run]), future_runs[run])
                for run in not_done
            )
            runs: list[ShellRun] = [future_runs[f] for f in done]  # type: ignore
        else:
            for run in runs:
                if run.is_running:
                    kill(run, immediate=True, reason="timeout")

    for run in runs:
        if error := run_error(run):
            errors.append((error, run))
        else:
            oks.append(run)
    return oks, errors


def kill_all_runs(
    immediate: bool = False,
    reason: str = "",
    abort_timeout: float = 3.0,
    *,
    skip_retry: bool = False,
):
    for run in list(_runs.values()):
        kill(
            run,
            immediate=immediate,
            reason=reason,
            abort_timeout=abort_timeout,
        )
    if len(_runs) > 0:
        logger.warning(
            f"still {_runs} runs left after killing, maybe some were started again, will try to kill them again"
        )
        if not skip_retry:
            kill_all_runs(
                immediate=True,
                reason=f"try-again kill all: {reason}",
                abort_timeout=abort_timeout,
                skip_retry=True,  # avoid infinite recursion if some runs are still running after this kill attempt
            )


def kill(
    run: ShellRun,
    immediate: bool = False,
    reason: str = "",
    abort_timeout: float = 3.0,
):
    """https://stackoverflow.com/questions/4789837/how-to-terminate-a-python-subprocess-launched-with-shell-true"""
    proc = run.p_open
    if not proc or proc.returncode is not None:
        logger.info(f"killing run already completed: {run} {reason}")
        return

    logger.warning(f"killing starting: {run} {reason}")
    try:
        pgid = os.getpgid(proc.pid)
        # proc.terminate() and proc.send_signal() doesn't work across platforms.
        if immediate:
            os.killpg(pgid, signal.SIGTERM)
        else:
            os.killpg(pgid, signal.SIGINT)
        proc.wait(timeout=abort_timeout)
        logger.info(f"killing completed: {run} {reason}")
    except subprocess.TimeoutExpired:
        logger.warning(
            f"killing timeout after {abort_timeout}s! forcing a kill: {run} {reason}"
        )
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        with suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=1)
    except (OSError, ValueError) as e:
        logger.warning(f"unable to get output when shutting down: {run} {e!r}")
    finally:
        run.wait_until_complete(timeout=1, no_raise=True)


def _execute_run(shell_run: ShellRun) -> ShellRun:
    """
    Principles:
    1. This function is executed in a separate thread. Interrupts will not affect it.
    2. It should handle every error condition and not raise exceptions.
    """
    config = shell_run.config
    queue = shell_run._queue

    def queue_consumer():
        for message in queue:
            try:
                shell_run._on_event(message)
            except BaseException as e:
                logger.warning(
                    f"Error processing message '{type(message).__name__}' for {shell_run}: {e!r}"
                )
                logger.exception(e)

    try:
        shell_run._on_event(
            ShellRunBefore(run=shell_run)
        )  # can block, for example if the thread pool doesn't have enough threads free
    except BaseException as e:
        logger.warning(f"Error before starting run {shell_run}: {e!r}")
        shell_run._complete(error=e)
        return shell_run

    consumer_future = _pool.submit(queue_consumer)
    output_dir = config.run_output_dir_resolved()
    output_dir.mkdir(parents=True, exist_ok=True)
    error: BaseException | None = None
    for attempt in range(1, config.attempts + 1):
        if attempt > 1:
            queue.put_nowait(ShellRunRetryAttempt(attempt=attempt))
            logger.warning(
                f"Retrying run {shell_run} attempt {attempt} of {config.attempts}"
            )
        attempt_log_prefix = config.run_log_stem(attempt)

        result = _attempt_run(shell_run, output_dir, attempt_log_prefix)
        match result:
            case ShellRun() if result.clean_complete or not config.should_retry(result):
                break
            case BaseException():
                error = result
                break
    queue.put_nowait(ShellRunAfter(run=shell_run, error=error))
    shell_run._complete(error=error, queue_consumer=consumer_future)
    return shell_run


def _attempt_run(
    shell_run: ShellRun,
    output_dir: Path,
    file_name: str,
) -> ShellRun | BaseException:
    """Run the shell command and handle the error, never raises an exception."""
    config = shell_run.config
    key = id(shell_run)
    _runs[key] = shell_run
    try:
        _run(
            config,
            shell_run._queue,
            output_dir,
            file_name,
        )
        return shell_run
    except BaseException as e:
        logger.warning(f"Error running {shell_run}: {e!r}")
        logger.exception(e)
        return e
    finally:
        _runs.pop(key, None)


def _run(
    config: ShellConfig,
    queue: ShellRunQueueT,
    output_dir: Path,
    file_name: str,
) -> None:
    kwargs = (
        dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=setsid,
            universal_newlines=True,
        )
        | config.popen_kwargs
    )
    with subprocess.Popen(config.shell_input, shell=True, **kwargs) as proc:  # type: ignore
        queue.put_nowait(ShellRunPOpenStarted(proc))

        def stdout_started(is_stdout: bool, console: Console, log_path: Path):
            queue.put_nowait(
                ShellRunStdStarted(
                    is_stdout=is_stdout, console=console, log_path=log_path
                )
            )

        def add_stdout_line(line: str):
            queue.put_nowait(ShellRunStdOutput(is_stdout=True, content=line))

        def read_stdout():
            output_path = output_dir / f"{file_name}.stdout.log"
            try:
                _read_until_complete(
                    stream=proc.stdout,  # type: ignore
                    output_path=output_path,
                    on_console_ready=lambda console: stdout_started(
                        is_stdout=True, console=console, log_path=output_path
                    ),
                    on_line=add_stdout_line,
                    config=config,
                )
            except BaseException as e:
                logger.exception(e)
                queue.put_nowait(ShellRunStdReadError(is_stdout=True, error=e))

        def add_stderr_line(line: str):
            queue.put_nowait(ShellRunStdOutput(is_stdout=False, content=line))

        def read_stderr():
            output_path = output_dir / f"{file_name}.stderr.log"
            try:
                _read_until_complete(
                    stream=proc.stderr,  # type: ignore
                    output_path=output_path,
                    on_console_ready=lambda console: stdout_started(
                        is_stdout=False, console=console, log_path=output_path
                    ),
                    on_line=add_stderr_line,
                    config=config,
                )
            except BaseException as e:
                logger.exception(e)
                queue.put_nowait(ShellRunStdReadError(is_stdout=False, error=e))

        fut_stdout = _pool.submit(read_stdout)
        fut_stderr = _pool.submit(read_stderr)
        # no proc.wait/communicate, not sure if it will work
        wait([fut_stdout, fut_stderr])


def _read_until_complete(
    stream: IO[str],
    output_path: Path,
    on_console_ready: Callable[[Console], None],
    on_line: Callable[[str], None],
    config: ShellConfig,
):
    with open(output_path, "w") as f:
        console = Console(
            file=f,
            record=True,
            log_path=False,
            soft_wrap=True,
            log_time=config.include_log_time,
            width=config.terminal_width,
            markup=config.ansi_content,
        )
        on_console_ready(console)
        old_write = f.write

        def write_hook(text: str):
            text_no_extras = [line.strip() for line in text.splitlines()]
            return old_write("\n".join(text_no_extras))

        decoder = AnsiDecoder()

        def write_hook_ansi(text: str):
            try:
                plain_text = "\n".join(
                    decoder.decode_line(line).plain.strip()
                    for line in text.splitlines()
                )
            except MarkupError:
                return old_write(text)
            return old_write(plain_text)

        f.write = write_hook_ansi if config.ansi_content else write_hook
        if config.user_input:
            out_stream = sys.stdout if ".stdout." in output_path.name else sys.stderr

            def _on_line(line: str):
                console.log(line, end="")
                on_line(line)

            def _on_char(char: str):
                out_stream.write(char)
                out_stream.flush()

            _stream_one_character_at_a_time(
                stream,
                on_line=_on_line,
                on_char=_on_char,
            )
        else:
            for line in iter(stream.readline, ""):
                console.log(line, end="")
                on_line(line)


def _stream_one_character_at_a_time(
    stream: IO[str], on_line: Callable[[str], None], on_char: Callable[[str], Any]
):
    buffer = ""
    while True:
        chunk = stream.read(1)  # Read one character at a time
        if not chunk:
            break
        buffer += chunk
        on_char(chunk)
        if chunk == "\n":
            on_line(buffer)
            buffer = ""
    if buffer:  # Handle any remaining data (incomplete line)
        on_line(buffer)
