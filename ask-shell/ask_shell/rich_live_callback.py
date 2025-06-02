from __future__ import annotations

from dataclasses import dataclass, field

from ask_shell.models import (
    AfterRunMessage,
    BeforeRunMessage,
    InternalMessageT,
    ShellRun,
)
from ask_shell.rich_live import live_frozen
from ask_shell.rich_run_state import _RunInfo, _RunState


@dataclass
class RunConsoleLogger:
    state: _RunState = field(default_factory=_RunState, init=False)
    frozen: live_frozen | None = field(default=None, init=False)

    @property
    def runs(self) -> list[ShellRun]:
        return [info.run for info in self.state.runs.values()]

    @property
    def no_user_input_runs(self) -> bool:
        return not any(run.config.user_input for run in self.runs)

    def __call__(self, message: InternalMessageT) -> bool:
        match message:
            case BeforeRunMessage(run=run):
                run_id = id(run)
                if run_id in self.state.runs:
                    return False  # Run already exists, no need to add again
                self.state.runs[run_id] = _RunInfo(run=run)
                if run.config.user_input and self.frozen is None:
                    self.frozen = live_frozen()
                    self.frozen.__enter__()
            case AfterRunMessage(run=run):
                self.state.runs.pop(id(run), None)
                if self.frozen is not None and self.no_user_input_runs:
                    self.frozen.__exit__(None, None, None)
                    self.frozen = None
        return False


_logger = RunConsoleLogger()


def callback(message: InternalMessageT) -> bool:
    return _logger(message)
