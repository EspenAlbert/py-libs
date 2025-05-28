from __future__ import annotations

import atexit
import logging
import signal
import subprocess
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import contextmanager
from os import getenv, setsid
from pathlib import Path
from typing import IO, Callable

from model_lib.pydantic_utils import copy_and_validate
from rich.console import Console

from ask_shell.colors import ContentType
from ask_shell.models import (
    RunIncompleteError,
    ShellConfig,
    ShellError,
    ShellRun,
    ShellRunQueueT,
    _pOpenStarted,
    _stdOutput,
    _stdStarted,
)
from ask_shell.printer import log_exception, print_with
from ask_shell.settings import AskShellSettings

logger = logging.getLogger(__name__)
_STDOUT = ContentType.STDOUT
_STDERR = ContentType.STDERR
_ERROR = ContentType.ERROR
_WARNING = ContentType.WARNING
_pool = ThreadPoolExecutor(
    max_workers=int(getenv("RUN_THREAD_COUNT", "50"))
)  # Each run will take 3 threads: 1 for stdout, 1 for stderr, and 1 for popen wait.
_runs: dict[
    int, ShellRun
] = {}  # internal to store running ShellRuns to support stopping them on exit


def stop_runs_and_pool():
    print_with(
        "STOPPING stop_runs_and_pool", prefix="_ask_shell", content_type=_WARNING
    )
    kill_all_runs(reason="atexit")
    _pool.shutdown(wait=True)


atexit.register(stop_runs_and_pool)


def run(
    config: ShellConfig | str,
    *,
    env: dict[str, str] | None = None,
    skip_os_env: bool | None = None,
    cwd: str | Path | None = None,
    attempts: int | None = None,
    print_prefix: str | None = None,
    extra_popen_kwargs: dict | None = None,
    allow_non_zero_exit: bool | None = None,
    should_retry: Callable[[ShellRun], bool] | None = None,
    ansi_content: bool | None = None,
    skip_binary_check: bool | None = None,
    start_timeout: float | None = None,
    settings: AskShellSettings | None = None,
) -> ShellRun:
    config = _as_config(
        config,
        env=env,
        skip_os_env=skip_os_env,
        cwd=cwd,
        attempts=attempts,
        print_prefix=print_prefix,
        extra_popen_kwargs=extra_popen_kwargs,
        allow_non_zero_exit=allow_non_zero_exit,
        should_retry=should_retry,
        ansi_content=ansi_content,
        skip_binary_check=skip_binary_check,
        settings=settings,
    )
    run = ShellRun(config)
    _pool.submit(_execute_run, run)
    return run.wait_on_started(start_timeout)


def run_and_wait(
    script: ShellConfig | str,
    timeout: float | None = None,
    *,
    env: dict[str, str] | None = None,
    skip_os_env: bool | None = None,
    cwd: str | Path | None = None,
    attempts: int | None = None,
    print_prefix: str | None = None,
    extra_popen_kwargs: dict | None = None,
    allow_non_zero_exit: bool | None = None,
    should_retry: Callable[[ShellRun], bool] | None = None,
    ansi_content: bool | None = None,
    skip_binary_check: bool | None = None,
    settings: AskShellSettings | None = None,
) -> ShellRun:
    config = _as_config(
        script,
        env=env,
        skip_os_env=skip_os_env,
        cwd=cwd,
        attempts=attempts,
        print_prefix=print_prefix,
        extra_popen_kwargs=extra_popen_kwargs,
        allow_non_zero_exit=allow_non_zero_exit,
        should_retry=should_retry,
        ansi_content=ansi_content,
        skip_binary_check=skip_binary_check,
        settings=settings,
    )
    run = ShellRun(config)
    _pool.submit(_execute_run, run)
    run.wait_until_complete(timeout)
    return run


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
                if run.is_running and (p_open := run.p_open):
                    prefix = run.config.print_prefix
                    kill(p_open, immediate=True, reason="timeout", prefix=prefix)

    for run in runs:
        if error := run_error(run):
            errors.append((error, run))
        else:
            oks.append(run)
    return oks, errors


def kill_all_runs(
    immediate: bool = False, reason: str = "", abort_timeout: float = 3.0
):
    for run in _runs.values():
        if p_open := run.p_open:
            kill(
                p_open,
                immediate=immediate,
                reason=reason,
                abort_timeout=abort_timeout,
                prefix=run.config.print_prefix,
            )


def kill(
    proc: subprocess.Popen,
    immediate: bool = False,
    reason: str = "",
    prefix: str = "",
    abort_timeout: float = 3.0,
):
    """https://stackoverflow.com/questions/4789837/how-to-terminate-a-python-subprocess-launched-with-shell-true"""
    if proc.returncode is not None:
        # already finished
        return

    def warn(message: str):
        print_with(message, prefix=prefix, content_type=_WARNING)

    warn(f"killing: {reason}")
    try:
        if immediate:
            proc.terminate()
        else:
            proc.send_signal(signal.SIGINT)
        proc.wait(timeout=abort_timeout)
        warn("killing complete")
    except subprocess.TimeoutExpired:
        warn(f"timeout after {abort_timeout}s! forcing a kill")
        proc.terminate()
    except (OSError, ValueError) as e:
        warn(f"unable to get output when shutting down {e!r}")


@contextmanager
def _track_run(shell_run: ShellRun):
    key = id(shell_run)
    _runs[key] = shell_run
    try:
        yield
    except (KeyboardInterrupt, InterruptedError) as e:
        logger.info(f"interrupt: {e!r}")
        stop_runs_and_pool()
        shell_run._complete()
    finally:
        _runs.pop(key, None)


def _execute_run(shell_run: ShellRun) -> ShellRun:
    config = shell_run.config

    def queue_consumer():
        for message in shell_run._queue:
            try:
                shell_run._on_message(message)
            except BaseException as e:
                print_with(
                    f"Error processing message: {e!r}",
                    prefix=config.print_prefix,
                    content_type=_ERROR,
                )
                log_exception(e)

    _pool.submit(queue_consumer)

    output_dir = config.run_output_dir_resolved()
    output_dir.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, config.attempts + 1):
        prefix = config.print_prefix
        if attempt > 1:
            prefix += f"-{attempt}"
            print_with(f"attempt: {attempt}", prefix=prefix, content_type=_WARNING)
        is_last_attempt = attempt == config.attempts
        if result := _attempt_run(
            shell_run, prefix, is_last_attempt, output_dir, config.run_log_stem(attempt)
        ):
            return result
        if retry_call := config.should_retry:
            if not retry_call(shell_run):
                shell_run._complete()
                break
    return shell_run


def _attempt_run(
    shell_run: ShellRun,
    prefix: str,
    is_last_attempt: bool,
    output_dir: Path,
    file_name: str,
) -> ShellRun | None:
    """Returns a ShellRun when it completed successfully, otherwise None."""
    config = shell_run.config
    with _track_run(shell_run):
        try:
            _run(
                config.shell_input,
                shell_run._queue,
                config.popen_kwargs,
                config.ansi_content,
                output_dir,
                file_name,
            )
            if shell_run.clean_complete:
                shell_run._complete()
                return shell_run
            if is_last_attempt or config.allow_non_zero_exit:
                shell_run._complete()
        except Exception as e:
            print_with(repr(e), prefix=prefix, content_type=_ERROR)
            log_exception(e)
            if is_last_attempt:
                error = ShellError(shell_run, base_error=e)
                shell_run._complete(error)
                raise error from e
    return None


def _run(
    script: str,
    queue: ShellRunQueueT,
    kwargs: dict,
    ansi_content: bool,
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
        | kwargs
    )
    with subprocess.Popen(script, shell=True, **kwargs) as proc:  # type: ignore
        queue.put_nowait(_pOpenStarted(proc))

        def stdout_started(is_stdout: bool, console: Console):
            queue.put_nowait(_stdStarted(is_stdout=is_stdout, console=console))

        def add_stdout_line(line: str):
            queue.put_nowait(_stdOutput(is_stdout=True, content=line))

        def read_stdout():
            output_path = output_dir / f"{file_name}.stdout.log"
            _read_until_complete(
                stream=proc.stdout,  # type: ignore
                output_path=output_path,
                on_console_ready=lambda console: stdout_started(
                    is_stdout=True, console=console
                ),
                on_line=add_stdout_line,
            )

        def add_stderr_line(line: str):
            queue.put_nowait(_stdOutput(is_stdout=False, content=line))

        def read_stderr():
            output_path = output_dir / f"{file_name}.stderr.log"
            _read_until_complete(
                stream=proc.stderr,  # type: ignore
                output_path=output_path,
                on_console_ready=lambda console: stdout_started(
                    is_stdout=False, console=console
                ),
                on_line=add_stderr_line,
            )

        fut_stdout = _pool.submit(read_stdout)
        fut_stderr = _pool.submit(read_stderr)
        # no proc.wait/communicate, not sure if it will work
        wait([fut_stdout, fut_stderr])


def _read_until_complete(
    stream: IO[str],
    output_path: Path,
    on_console_ready: Callable[[Console], None],
    on_line: Callable[[str], None],
):
    # content_type = _STDOUT if is_stdout else _STDERR

    with open(output_path, "w") as f:
        console = Console(file=f, record=True, log_path=False, soft_wrap=True)
        on_console_ready(console)
        old_write = f.write

        def write_hook(text: str):
            # might need a different callback if ansi_content is True
            text_no_extras = [line.strip() for line in text.splitlines()]
            return old_write("\n".join(text_no_extras) + "\n")

        f.write = write_hook
        for line in iter(stream.readline, ""):
            console.log(line)
            on_line(line)
        # try:
        #     print_with(
        #         line.strip("\n"),
        #         prefix=prefix,
        #         content_type=content_type,
        #         ansi_content=ansi_content,
        #     )
        # except ValueError as e:
        #     if "I/O operation on closed file" in str(e):
        #         return
        #     print_with(repr(e), prefix=prefix, content_type=_ERROR)
        #     log_exception(e)
        # except BaseException as e:
        #     log_exception(e)
