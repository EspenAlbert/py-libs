from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.progress import (
    Progress,
    TextColumn,
    TimeElapsedColumn,
)

from ask_shell.models import (
    ShellRun,
    ShellRunEventT,
    ShellRunPOpenStarted,
    ShellRunRetryAttempt,
    ShellRunStdOutput,
    ShellRunStdReadError,
    ShellRunStdStarted,
)
from ask_shell.rich_progress import ProgressManager, log_task_done, new_task


def _deque_default() -> deque[str]:
    return deque(maxlen=30)


@dataclass
class _RunInfo:
    run: ShellRun
    stdout: deque[str] = field(default_factory=_deque_default)
    stderr: deque[str] = field(default_factory=_deque_default)

    log_path_stdout: Path | None = None
    log_path_stderr: Path | None = None

    error_read_stdout: BaseException | None = None
    error_read_stderr: BaseException | None = None
    started: bool = False
    attempt: int = 1

    task: new_task | None = field(default=None, init=False)  # managed by _RunState

    @property
    def stdout_str(self) -> str:
        return "".join(self.stdout)

    @property
    def stderr_str(self) -> str:
        return "".join(self.stderr)

    def __call__(self, message: ShellRunEventT) -> Any:
        match message:
            case ShellRunStdOutput(is_stdout=is_stdout, content=content):
                if is_stdout:
                    self.stdout.append(content)
                else:
                    self.stderr.append(content)
            case ShellRunStdStarted(is_stdout=is_stdout, log_path=log_path):
                if is_stdout:
                    self.log_path_stdout = log_path
                else:
                    self.log_path_stderr = log_path
            case ShellRunPOpenStarted():
                self.started = True
            case ShellRunRetryAttempt(attempt=attempt):
                self.attempt = attempt
            case ShellRunStdReadError(is_stdout=is_stdout, error=error):
                if is_stdout:
                    self.error_read_stdout = error
                else:
                    self.error_read_stderr = error


def progress_for_runs() -> Progress:
    return Progress(
        TextColumn("[bold purple]{task.description}"),
        TimeElapsedColumn(),
        TextColumn(
            "{task.fields[stdout]}", markup=False
        ),  # Risks getting hard to debug logs as we don't control the stdout/stderr if markup is enabled
        TextColumn(
            "{task.fields[stderr]}", markup=False
        ),  # Risks getting hard to debug logs as we don't control the stdout/stderr if markup is enabled
    )


def manager_for_runs() -> ProgressManager:
    return ProgressManager(title="Shell Runs", progress_constructor=progress_for_runs)


@dataclass
class _RunState:
    runs: dict[int, _RunInfo] = field(default_factory=dict, repr=False)
    _progress_manager: ProgressManager = field(
        init=False, repr=False, default_factory=manager_for_runs
    )

    @property
    def active_runs(self) -> list[ShellRun]:
        return [info.run for info in self.runs.values()]

    @property
    def no_user_input_runs(self) -> bool:
        return not any(run.config.user_input for run in self.active_runs)

    def add_run(self, run: ShellRun) -> None:
        run_id = id(run)
        if run_id in self.runs:
            return  # Run already exists, no need to add it again
        self.runs[id(run)] = run_info = _RunInfo(run=run)
        task = new_task(
            description=run.config.print_prefix,
            total=1,
            task_fields={
                "stdout": "",
                "stderr": "",
            },
            log_after_remove=False,
            manager=self._progress_manager,
        )
        task.__enter__()
        run_info.task = task

        output_skipped = run.config.skip_progress_output

        def task_callback(message: ShellRunEventT) -> None:
            run_info(message)
            if not task.is_finished:
                task.update(
                    stdout="..." if output_skipped else run_info.stdout_str,
                    stderr="" if output_skipped else run_info.stderr_str,
                )

        run.config.message_callbacks.append(task_callback)

    def remove_run(self, run: ShellRun, error: BaseException | None = None) -> None:
        run_info = self.runs.pop(id(run), None)
        assert run_info is not None, "Run info should not be None when removing run"
        task = run_info.task
        assert task is not None, "Task should not be None when removing run"
        if error:
            run_info.stderr.append(f"run error: {error}")
            task.update(stderr=run_info.stderr_str)
        task.__exit__(None, None, None)
        run = run_info.run
        log_task_done(
            task,
            force_error=not run.clean_complete,
            description_override=f"'{run.config.shell_input}'",
            extra_parts=[
                "" if run._current_attempt == 1 else f"attempt {run._current_attempt}",
            ],
        )
