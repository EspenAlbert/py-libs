"""Inspired by: https://github.com/tmbo/questionary/blob/master/tests/utils.py"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from functools import wraps
from typing import Callable, Generic, TypeVar

from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output import DummyOutput
from pydantic import BaseModel, model_validator
from questionary import Choice, Question, checkbox
from questionary import confirm as _confirm
from questionary import select as _select
from questionary import text as _text
from zero_3rdparty.object_name import as_name, func_arg_names
from zero_3rdparty.str_utils import ensure_suffix

from ask_shell._internal._run import get_pool
from ask_shell._internal._run_env import (
    interactive_shell,
)
from ask_shell._internal.rich_live import pause_live
from ask_shell.settings import AskShellSettings, _global_settings

T = TypeVar("T")
TypedAsk = Callable[[Question, type[T]], T]
logger = logging.getLogger(__name__)
SEARCH_ENABLED_AFTER_CHOICES = _global_settings.search_enabled_after_choices


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
    assert "default" in func_arg_names(func), (
        f"Function {as_name(func)} must have a 'default' parameter"
    )

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


_PROMPT_TEXT_ATTR_NAME = "__prompt_text__"


def _set_prompt_text(q: Question, prompt_text: str) -> None:
    setattr(q, _PROMPT_TEXT_ATTR_NAME, prompt_text)


def confirm(prompt_text: str, *, default: bool | None = None) -> bool:
    if default is None:
        question = _confirm(prompt_text)
    else:
        question = _confirm(prompt_text, default=default)
    _set_prompt_text(question, prompt_text)
    return _question_asker(question, bool)


_unset = object()


class SelectChosenOptions(BaseModel):
    use_search_filter: bool
    use_shortcuts: bool
    use_jk_keys: bool


@dataclass
class NewHandlerChoice(Generic[T]):
    constructor: Callable[[str], T]
    new_prompt: str


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

    def as_choice(self) -> Choice:
        return Choice(
            title=self.name,
            value=self.value,
            description=self.description,
            checked=self.checked,
        )


@pause_live
@return_default_if_not_interactive
def text(
    prompt_text: str,
    default: str = "",
) -> str:
    question = _text(prompt_text, default=default)
    _set_prompt_text(question, prompt_text)
    return _question_asker(question, str)


class SelectOptions(BaseModel, Generic[T]):
    use_search_filter: bool | object = _unset
    use_shortcuts: bool | object = _unset
    use_jk_keys: bool | object = _unset
    new_handler_choice: NewHandlerChoice[T] | None = None

    @property
    def allow_new(self) -> bool:
        return self.new_handler_choice is not None

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

    def _ask_for_new_value(self) -> T:
        new_handler_choice = self.new_handler_choice
        assert new_handler_choice, (
            "Should never happen, new_handler_choice must be set when allow_new is True"
        )
        new_text = text(new_handler_choice.new_prompt)
        return new_handler_choice.constructor(new_text)

    def _select(self, prompt_text: str, choices: list[ChoiceTyped[T]]) -> T:
        chosen = self.set_defaults(len(choices))
        if self.allow_new:
            prompt_text += " (use ctrl+c to define a new instead)"
        _questionary_choices = [typed_choice.as_choice() for typed_choice in choices]
        question = _select(
            prompt_text,
            default=next(
                (choice for choice in _questionary_choices if choice.checked), None
            ),
            choices=_questionary_choices,
            use_jk_keys=chosen.use_jk_keys,
            use_shortcuts=chosen.use_shortcuts,
            use_search_filter=chosen.use_search_filter,
        )
        _set_prompt_text(question, prompt_text)
        try:
            return _question_asker(question, T)
        except KeyboardInterrupt:
            if not self.allow_new:
                raise
            return self._ask_for_new_value()

    def _select_multiple(
        self, prompt_text: str, choices: list[ChoiceTyped[T]]
    ) -> list[T]:
        chosen = self.set_defaults(len(choices))
        if self.allow_new:
            prompt_text = ensure_suffix(prompt_text, " (use ctrl+c to add new choice)")
        question = checkbox(
            prompt_text,
            choices=[typed_choice.as_choice() for typed_choice in choices],
            use_jk_keys=chosen.use_jk_keys,
            use_search_filter=chosen.use_search_filter,
        )
        _set_prompt_text(question, prompt_text)
        try:
            return _question_asker(question, list[T])
        except KeyboardInterrupt:
            if not self.allow_new:
                raise
            new_option = self._ask_for_new_value()
            new_choice = ChoiceTyped(
                str(new_option),
                value=new_option,
                description="just added",
                checked=True,
            )
            choices.insert(0, new_choice)
            return self._select_multiple(prompt_text, choices=choices)


@pause_live
@return_default_if_not_interactive
def select_list_multiple(
    prompt_text: str,
    choices: list[str],
    *,
    default: list[str] | None = None,
    options: SelectOptions | None = None,
) -> list[str]:
    assert choices, f"choices must not be empty for {as_name(select_list_multiple)}"
    options = options or SelectOptions()
    default = default or []
    default_choices = [
        ChoiceTyped(option, checked=option in default, value=option)
        for option in choices
    ]
    return options._select_multiple(prompt_text, default_choices)


@pause_live
@return_default_if_not_interactive
def select_list_multiple_choices(
    prompt_text: str,
    choices: list[ChoiceTyped[T]],
    default: list[T]
    | None = None,  # return if not interactive and not None, use choices.*.checked to set the actual default
    *,
    options: SelectOptions | None = None,
) -> list[T]:
    assert choices, (
        f"choices must not be empty for {as_name(select_list_multiple_choices)}"
    )
    options = options or SelectOptions()
    return options._select_multiple(prompt_text, choices)


@pause_live
@return_default_if_not_interactive
def select_dict(
    prompt_text: str,
    choices: dict[str, T],
    *,
    default: str | None = None,
    options: SelectOptions | None = None,
) -> T:
    assert choices, f"choices must not be empty for {as_name(select_dict)}"
    options = options or SelectOptions()
    default_safe = default or ""
    choices_typed = [
        ChoiceTyped(name=key, value=value, checked=key == default_safe)
        for key, value in choices.items()
    ]
    return options._select(prompt_text, choices_typed)


@pause_live
@return_default_if_not_interactive
def select_list(
    prompt_text: str,
    choices: list[str],
    *,
    default: str | None = None,
    options: SelectOptions | None = None,
) -> str:
    assert choices, f"choices must not be empty for {as_name(select_list)}"
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
    assert choices, f"choices must not be empty for {as_name(select_list_choice)}"
    options = options or SelectOptions()
    return options._select(prompt_text, choices)


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


def _get_prompt_text(q: Question) -> str:
    return getattr(q, _PROMPT_TEXT_ATTR_NAME, "")


@dataclass
class PromptMatch:
    substring: str = ""
    exact: str = ""
    max_matches: int = 1
    matches_so_far: int = field(init=False, default=0)

    @property
    def match_exhausted(self) -> bool:
        return self.matches_so_far >= self.max_matches

    def __call__(self, prompt_text: str) -> bool:
        if self.match_exhausted:
            return False
        if (substr := self.substring) and substr in prompt_text:
            self.matches_so_far += 1
            return True
        if (exact := self.exact) and exact == prompt_text:
            self.matches_so_far += 1
            return True
        return False

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, PromptMatch):
            return NotImplemented
        return (
            self.substring == value.substring
            and self.exact == value.exact
            and self.max_matches == value.max_matches
        )

    def __hash__(self) -> int:
        return hash((self.substring, self.exact, self.max_matches))


@dataclass
class question_patcher:
    """Context manager to patch the questionary.ask_question, useful for testing."""

    responses: list[str] = field(default_factory=list)
    next_response: int = 0
    dynamic_responses: dict[PromptMatch, str] = field(default_factory=dict)
    settings: AskShellSettings = field(default_factory=AskShellSettings.from_env)

    _old_force_interactive_env_str: str = field(default="", init=False, repr=False)

    def _dynamic_match(self, prompt_text: str) -> str | None:
        return next(
            (
                response
                for matcher, response in self.dynamic_responses.items()
                if matcher(prompt_text)
            ),
            None,
        )

    def _next_index_response(self, prompt_text: str) -> str:
        try:
            input_response = self.responses[self.next_response]
        except IndexError:
            raise ValueError(
                f"Not enough responses provided. Expected {len(self.responses)}, got {self.next_response + 1} questions. Last prompt: '{prompt_text}'"
            )
        self.next_response += 1
        return input_response

    def _next_response(self, q: Question) -> str:
        if prompt_text := _get_prompt_text(q):
            if dynamic := self._dynamic_match(prompt_text):
                return dynamic
            return self._next_index_response(prompt_text)
        return self._next_index_response("")

    def ask_question(self, q: Question, response_type: type[T]) -> T:
        q.application.output = DummyOutput()

        def run(inp) -> T:
            input_response = self._next_response(q)
            inp.send_text(input_response + KeyInput.ENTER + "\r")
            q.application.output = DummyOutput()
            q.application.input = inp
            return _default_asker(q, response_type)

        with create_pipe_input() as inp:
            return run(inp)

    def __enter__(self):
        global _question_asker
        self._old_patcher = _question_asker
        _question_asker = self.ask_question
        self._old_force_interactive_env_str = str(self.settings.force_interactive_shell)
        interactive_shell.cache_clear()
        os.environ[self.settings.ENV_NAME_FORCE_INTERACTIVE_SHELL] = "true"
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _question_asker
        _question_asker = self._old_patcher
        os.environ[self.settings.ENV_NAME_FORCE_INTERACTIVE_SHELL] = (
            self._old_force_interactive_env_str
        )
        interactive_shell.cache_clear()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    new_handler = NewHandlerChoice(str, new_prompt="choose different value")
    logger.info(
        select_list_choice(
            "select me",
            [ChoiceTyped(name="c1", value=1), ChoiceTyped(name="c2", value=2)],
            options=SelectOptions(new_handler_choice=new_handler),
        )
    )

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
