"""Inspired by: https://github.com/tmbo/questionary/blob/master/tests/utils.py"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from functools import wraps
from os import getenv
from typing import Callable, Generic, TypeVar

from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output import DummyOutput
from pydantic import BaseModel, model_validator
from questionary import Choice, Question, checkbox
from questionary import confirm as _confirm
from questionary import select as _select
from questionary import text as _text
from zero_3rdparty.object_name import as_name, func_arg_names

from ask_shell._run import get_pool
from ask_shell._run_env import ENV_NAME_FORCE_INTERACTIVE_SHELL, interactive_shell
from ask_shell.rich_live import pause_live
from ask_shell.settings import AskShellSettings

T = TypeVar("T")
TypedAsk = Callable[[Question, type[T]], T]
logger = logging.getLogger(__name__)
SEARCH_ENABLED_AFTER_CHOICES = int(
    getenv(AskShellSettings.ENV_NAME_SEARCH_ENABLED_AFTER_CHOICES, "7")
)


def _default_asker(q: Question, _: type[T]) -> T:
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        return q.unsafe_ask()

    # Run blocking call in separate thread to avoid error: # RuntimeError: This event loop is already running
    return get_pool().submit(q.unsafe_ask).result()


_question_asker: TypedAsk = _default_asker


FuncT = TypeVar("FuncT", bound=Callable)


def return_default_if_not_interactive(func: FuncT) -> FuncT:
    assert "default" in func_arg_names(func)

    @wraps(func)
    def return_default(*args, **kwargs):
        if interactive_shell():
            return func(*args, **kwargs)
        default_value = kwargs.get("default", None)
        if default_value is None:
            raise ValueError(
                f"Function called in non-interactive shell, but no default value provided &func={as_name(func)}"
            )
        logger.warning(
            f"Function {as_name(func)} called in non-interactive shell, returning default value: {default_value}"
        )
        return default_value

    return return_default  # type: ignore


@pause_live
@return_default_if_not_interactive
def confirm(prompt_text: str, *, default: bool | None = None) -> bool:
    if default is None:
        return _question_asker(_confirm(prompt_text), bool)
    return _question_asker(_confirm(prompt_text, default=default), bool)


@pause_live
@return_default_if_not_interactive
def select_list_multiple(
    prompt_text: str,
    choices: list[str],
    *,
    default: list[str] | None = None,
    options: SelectOptions | None = None,
) -> list[str]:
    assert choices, "choices must not be empty"
    options = options or SelectOptions()
    chosen = options.set_defaults(len(choices))
    default = default or []
    default_choices = [Choice(option, checked=option in default) for option in choices]
    return _question_asker(
        checkbox(
            prompt_text,
            choices=default_choices,
            use_jk_keys=chosen.use_jk_keys,
            use_search_filter=chosen.use_search_filter,
        ),
        list[str],
    )


@dataclass
class ChoiceTyped(Generic[T]):
    name: str
    value: T
    description: str | None = None
    checked: bool = False

    @classmethod
    def from_descriptions(cls, descriptions: dict[str, str]) -> list[ChoiceTyped[str]]:
        return [
            cls(name=name, value=name, description=description)  # type: ignore
            for name, description in descriptions.items()
        ]  # type: ignore


@pause_live
@return_default_if_not_interactive
def select_list_multiple_choices(
    prompt_text: str,
    choices: list[ChoiceTyped[T]],
    default: list[T] | None = None,  # return if not interactive and not None
    *,
    options: SelectOptions | None = None,
) -> list[T]:
    assert choices, "choices must not be empty"
    options = options or SelectOptions()
    chosen = options.set_defaults(len(choices))
    return _question_asker(
        checkbox(
            prompt_text,
            choices=[
                Choice(
                    typed_choice.name,
                    value=typed_choice.value,
                    description=typed_choice.description,
                    checked=typed_choice.checked,
                )
                for typed_choice in choices
            ],
            use_jk_keys=chosen.use_jk_keys,
            use_search_filter=chosen.use_search_filter,
        ),
        list[T],
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


@pause_live
@return_default_if_not_interactive
def text(
    prompt_text: str,
    default: str = "",
) -> str:
    return _question_asker(_text(prompt_text, default=default), str)


T = TypeVar("T")


@pause_live
@return_default_if_not_interactive
def select_dict(
    prompt_text: str,
    choices: dict[str, T],
    *,
    default: str | None = None,
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


@pause_live
@return_default_if_not_interactive
def select_list(
    prompt_text: str,
    choices: list[str],
    *,
    default: str | None = None,
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


@pause_live
@return_default_if_not_interactive
def select_list_choice(
    prompt_text: str,
    choices: list[ChoiceTyped[T]],
    *,
    default: T | None = None,
    options: SelectOptions | None = None,
) -> T:
    assert choices, "choices must not be empty"
    options = options or SelectOptions()
    chosen = options.set_defaults(len(choices))
    return _question_asker(
        _select(
            prompt_text,
            default=default,  # type: ignore
            choices=[
                Choice(
                    typed_choice.name,
                    value=typed_choice.value,
                    description=typed_choice.description,
                )
                for typed_choice in choices
            ],
            use_jk_keys=chosen.use_jk_keys,
            use_shortcuts=chosen.use_shortcuts,
            use_search_filter=chosen.use_search_filter,
        ),
        T,
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
    """Context manager to patch the questionary.ask_question, useful for testing."""

    responses: list[str]
    next_response: int = 0

    _old_force_interactive_env_str: str = field(default="", init=False, repr=False)

    def __enter__(self):
        global _question_asker
        self._old_patcher = _question_asker
        _question_asker = self.ask_question
        self._old_force_interactive_env_str = getenv(
            ENV_NAME_FORCE_INTERACTIVE_SHELL, ""
        )
        interactive_shell.cache_clear()
        os.environ[ENV_NAME_FORCE_INTERACTIVE_SHELL] = "true"
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _question_patcher
        _question_patcher = self._old_patcher
        os.environ[ENV_NAME_FORCE_INTERACTIVE_SHELL] = (
            self._old_force_interactive_env_str
        )
        interactive_shell.cache_clear()

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
            return _default_asker(q, response_type)

        with create_pipe_input() as inp:
            return run(inp)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def async_main():
        logger.info(
            f"Async confirm: {confirm('Can you confirm from async?', default=True)}"
        )

    asyncio.run(async_main())
    choices_typed = [
        ChoiceTyped(name="Option 1", value=1, description="First option"),
        ChoiceTyped(name="Option 2", value=2, description="Second option"),
    ]
    logger.info(
        select_list_multiple_choices("Select options:", choices_typed, default=[1])
    )
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
            "Select options:",
            ["Option 1", "Option 2", "Option 3"],
            default=["Option 1"],
        )
    )
    logger.info(text("Enter your name:", default="John Doe"))
