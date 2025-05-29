"""Inspired by: https://github.com/tmbo/questionary/blob/master/tests/utils.py"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, TypeVar

from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output import DummyOutput
from pydantic import BaseModel, model_validator
from questionary import Question, checkbox
from questionary import confirm as _confirm
from questionary import select as _select
from questionary import text as _text

from ask_shell.interactive_rich import ensure_progress_stopped

T = TypeVar("T")
TypedAsk = Callable[[Question, type[T]], T]
logger = logging.getLogger(__name__)
SEARCH_ENABLED_AFTER_CHOICES = 7


def _default_asker(q: Question, _: type[T]) -> T:
    # ensure progress bar doesn't refresh
    # add an extra \n before the question, looks like I should do that on the top level api methods instead
    return q.unsafe_ask()


_question_asker: TypedAsk = _default_asker


@ensure_progress_stopped
def confirm(prompt_text: str, *, default: bool | None = None) -> bool:
    if default is None:
        return _question_asker(_confirm(prompt_text), bool)
    return _question_asker(_confirm(prompt_text, default=default), bool)


@ensure_progress_stopped
def select_list_multiple(
    prompt_text: str,
    choices: list[str],
    default: list[str] | None = None,
    *,
    options: SelectOptions | None = None,
) -> list[str]:
    assert choices, "choices must not be empty"
    options = options or SelectOptions()
    chosen = options.set_defaults(len(choices))
    default = default or []
    return _question_asker(
        checkbox(
            prompt_text,
            choices=choices,
            use_jk_keys=chosen.use_jk_keys,
            use_search_filter=chosen.use_search_filter,
        ),
        list[str],
    )


_unset = object()


class SelectOptions(BaseModel):
    use_search_filter: bool | object = _unset
    use_shortcuts: bool | object = _unset
    use_jk_keys: bool | object = _unset

    @model_validator(mode="after")
    def validate_compatibility(self) -> SelectOptions:
        if self.use_search_filter is True and self.use_jk_keys is True:
            raise ValueError(
                "use_search_filter and use_jk_keys cannot be used together"
            )
        return self

    def set_defaults(self, choices_length: int) -> SelectChosenOptions:
        if self.use_search_filter is _unset:
            if self.use_jk_keys is True:
                self.use_search_filter = False
            else:
                self.use_search_filter = choices_length > SEARCH_ENABLED_AFTER_CHOICES
        assert isinstance(self.use_search_filter, bool)
        if self.use_shortcuts is _unset:
            # search filter and shortcuts don't work well together
            self.use_shortcuts = (
                not self.use_search_filter
                and choices_length <= SEARCH_ENABLED_AFTER_CHOICES
            )
        assert isinstance(self.use_shortcuts, bool)
        if self.use_jk_keys is _unset:
            self.use_jk_keys = not self.use_search_filter
        assert isinstance(self.use_jk_keys, bool)
        return SelectChosenOptions(
            use_search_filter=self.use_search_filter,
            use_shortcuts=self.use_shortcuts,
            use_jk_keys=self.use_jk_keys,
        )


class SelectChosenOptions(BaseModel):
    use_search_filter: bool
    use_shortcuts: bool
    use_jk_keys: bool


@ensure_progress_stopped
def text(
    prompt_text: str,
    default: str = "",
) -> str:
    return _question_asker(_text(prompt_text, default=default), str)


T = TypeVar("T")


@ensure_progress_stopped
def select_dict(
    prompt_text: str,
    choices: dict[str, T],
    default: str | None = None,
    *,
    options: SelectOptions | None = None,
) -> T:
    assert choices, "choices must not be empty"
    options = options or SelectOptions()
    chosen = options.set_defaults(len(choices))
    selection = _question_asker(
        _select(
            prompt_text,
            default=default,
            choices=list(choices),
            use_jk_keys=chosen.use_jk_keys,
            use_shortcuts=chosen.use_shortcuts,
            use_search_filter=chosen.use_search_filter,
        ),
        str,
    )
    return choices[selection]


@ensure_progress_stopped
def select_list(
    prompt_text: str,
    choices: list[str],
    default: str | None = None,
    *,
    options: SelectOptions | None = None,
) -> str:
    assert choices, "choices must not be empty"
    options = options or SelectOptions()
    chosen = options.set_defaults(len(choices))
    return _question_asker(
        _select(
            prompt_text,
            default=default,
            choices=choices,
            use_jk_keys=chosen.use_jk_keys,
            use_shortcuts=chosen.use_shortcuts,
            use_search_filter=chosen.use_search_filter,
        ),
        str,
    )


class KeyInput:
    DOWN = "\x1b[B"
    UP = "\x1b[A"
    LEFT = "\x1b[D"
    RIGHT = "\x1b[C"
    ENTER = "\r"
    ESCAPE = "\x1b"
    CONTROLC = "\x03"
    CONTROLN = "\x0e"
    CONTROLP = "\x10"
    BACK = "\x7f"
    SPACE = " "
    TAB = "\x09"
    ONE = "1"
    TWO = "2"
    THREE = "3"


@dataclass
class question_patcher:
    responses: list[str]
    next_response: int = 0

    def __enter__(self):
        global _question_asker
        self._old_patcher = _question_asker
        _question_asker = self.ask_question
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _question_patcher
        _question_patcher = self._old_patcher

    def ask_question(self, q: Question, response_type: type[T]) -> T:
        q.application.output = DummyOutput()

        def run(inp) -> T:
            try:
                input_response = self.responses[self.next_response]
            except IndexError:
                raise ValueError(
                    f"Not enough responses provided. Expected {len(self.responses)}, got {self.next_response + 1} questions."
                )
            self.next_response += 1
            inp.send_text(input_response + KeyInput.ENTER + "\r")
            q.application.output = DummyOutput()
            q.application.input = inp
            return q.unsafe_ask()

        with create_pipe_input() as inp:
            return run(inp)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info(select_list("Choose a letter", list("abcdefghijklmnopqrstuvwxyz")))
    logger.info(
        select_dict(
            "Select an option:",
            {"Option 1": "1", "Option 2": "2", "Option 3": "3", "Are we done?": "done"},
            default="Option 3",
        )
    )
    logger.info(select_list("Select an option:", ["Option 1", "Option 2", "Option 3"]))
    logger.info(confirm("Can you confirm?", default=True))
    logger.info(text("Enter your name:", default="Espen"))
    logger.info(confirm("Can you confirm?", default=False))
    logger.info(
        select_list_multiple(
            "Select options:", ["Option 1", "Option 2", "Option 3"], ["Option 1"]
        )
    )
    logger.info(text("Enter your name:", default="John Doe"))
