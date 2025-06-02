from __future__ import annotations

from dataclasses import dataclass, field

from ask_shell.models import (
    AfterRunMessage,
    BeforeRunMessage,
    InternalMessageT,
)
from ask_shell.rich_live import live_frozen
from ask_shell.rich_run_state import _RunState


@dataclass
class RunConsoleLogger:
    state: _RunState = field(default_factory=_RunState, init=False)
    frozen: live_frozen | None = field(default=None, init=False)

    def __call__(self, message: InternalMessageT) -> bool:
        match message:
            case BeforeRunMessage(run=run):
                self.state.add_run(run)
                if run.config.user_input and self.frozen is None:
                    self.frozen = live_frozen()
                    self.frozen.__enter__()
            case AfterRunMessage(run=run, error=error):
                self.state.remove_run(run, error)
                if self.frozen is not None and self.state.no_user_input_runs:
                    self.frozen.__exit__(None, None, None)
                    self.frozen = None
        return False


_logger = RunConsoleLogger()


def rich_live_callback(message: InternalMessageT) -> bool:
    return _logger(message)
