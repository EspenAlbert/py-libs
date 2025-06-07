import pytest

from ask_shell.interactive import (
    SEARCH_ENABLED_AFTER_CHOICES,
    KeyInput,
    SelectOptions,
    confirm,
    question_patcher,
    select_dict,
    select_list,
    select_list_multiple,
    text,
)


def test_confirm():
    with question_patcher(["y", "n", "", ""]):
        assert confirm("Can you confirm? (should answer yes)")
        assert not confirm("Can you confirm? (should answer no)")
        assert confirm("Can you confirm? (use default yes)", default=True)
        assert not confirm("Can you confirm? (use default no)", default=False)


def test_text():
    with question_patcher(["Jane Doe", ""]):
        assert text("Enter your name:") == "Jane Doe"
        assert text("Enter your name:", default="John Doe") == "John Doe"
    with pytest.raises(KeyboardInterrupt):
        with question_patcher([KeyInput.CONTROLC]):
            text("Enter your name:")


@pytest.mark.parametrize(
    "inputs, options, expected",
    [
        ([""], ["Option 1", "Option 2"], []),
        ([" "], ["Option 1", "Option 2"], ["Option 1"]),
        ([f"{KeyInput.DOWN} "], ["Option 1", "Option 2"], ["Option 2"]),
        ([f" {KeyInput.DOWN} "], ["Option 1", "Option 2"], ["Option 1", "Option 2"]),
    ],
    ids=[
        "empty selection",
        "single selection",
        "second option selection",
        "multiple selection",
    ],
)
def test_select_list_multiple(inputs, options, expected):
    with question_patcher(inputs):
        assert select_list_multiple("Select options:", options) == expected


def test_select_list_multiple_with_default():
    with question_patcher([""]):
        options = ["Option 1", "Option 2", "Option 3"]
        assert (
            select_list_multiple("Select options:", options, default=options) == options
        )


@pytest.mark.parametrize(
    "inputs, options, default, expected",
    [
        ([""], ["Option 1", "Option 2", "Option 3"], None, "Option 1"),
        ([f"{KeyInput.DOWN}"], ["Option 1", "Option 2", "Option 3"], None, "Option 2"),
        ([""], ["Option 1", "Option 2", "Option 3"], "Option 2", "Option 2"),
        (
            [f"{KeyInput.DOWN}"],
            ["Option 1", "Option 2", "Option 3"],
            "Option 1",
            "Option 2",
        ),
        (
            [f"{KeyInput.DOWN}"],
            ["Option 1", "Option 2", "Option 3"],
            "Option 2",
            "Option 3",
        ),
    ],
    ids=[
        "first option no default",
        "second option no default",
        "option 2 is default and selected",
        "option 1 is default, select option 2",
        "option 2 is default, select option 3",
    ],
)
def test_select_list(inputs, options, default, expected):
    with question_patcher(inputs):
        assert select_list("Select an option:", options, default=default) == expected


def test_select_list_many_options_supports_search():
    with question_patcher(["q", ""]):
        assert select_list("Choose a letter", list("abcdefghijklmnopqrstuvwxyz")) == "q"


def test_select_list_supports_shortcut_on_shorter_lists():
    with question_patcher(["3"]):
        assert select_list("Choose a number", ["1", "2", "3"]) == "3"
    with question_patcher([f"{SEARCH_ENABLED_AFTER_CHOICES}"]):
        assert (
            select_list(
                "Choose a number",
                [str(i) for i in range(1, SEARCH_ENABLED_AFTER_CHOICES + 1)],
            )
            == f"{SEARCH_ENABLED_AFTER_CHOICES}"
        )


def test_explicit_select_options():
    with question_patcher(["j"]):
        assert (
            select_list(
                "Choose a letter",
                list("abcdefghijklmnopqrstuvwxyz"),
                options=SelectOptions(use_jk_keys=True),
            )
            == "b"
        )


def test_select_dict():
    with question_patcher(["", "Option 2"]):
        assert (
            select_dict(
                "Select an option:", {"Option 1": 1, "Option 2": 2}, default="Option 2"
            )
            == 2
        )
        assert select_dict("Select an option:", {"Option 1": 1, "Option 2": 2}) == 2


def test_SelectOptions_should_raise_value_error():
    with pytest.raises(ValueError):
        SelectOptions(use_search_filter=True, use_shortcuts=True, use_jk_keys=True)


def test_question_patcher_should_raise_value_error_when_there_are_no_more_input():
    with pytest.raises(ValueError):
        with question_patcher([]):
            select_list("Select an option:", ["Option 1", "Option 2"])


def test_return_default_if_not_interactive_should_raise_error_when_not_interactive():
    with pytest.raises(
        ValueError,
        match="Function called in non-interactive shell, but no default value provided",
    ):
        text("Are you sure?")
