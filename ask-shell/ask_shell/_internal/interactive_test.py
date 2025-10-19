import pytest

from ask_shell._internal.interactive import (
    SEARCH_ENABLED_AFTER_CHOICES,
    ChoiceTyped,
    KeyInput,
    NewHandlerChoice,
    PromptMatch,
    RaiseOnQuestionError,
    SelectOptions,
    confirm,
    question_patcher,
    raise_on_question,
    select_dict,
    select_list,
    select_list_choice,
    select_list_multiple,
    select_list_multiple_choices,
    text,
)


def test_confirm():
    with question_patcher(responses=["y", "n", "", ""]):
        assert confirm("Can you confirm? (should answer yes)")
        assert not confirm("Can you confirm? (should answer no)")
        assert confirm("Can you confirm? (use default yes)", default=True)
        assert not confirm("Can you confirm? (use default no)", default=False)


def test_text():
    with question_patcher(responses=["Jane Doe", ""]):
        assert text("Enter your name:") == "Jane Doe"
        assert text("Enter your name:", default="John Doe") == "John Doe"
    with pytest.raises(KeyboardInterrupt):
        with question_patcher(responses=[KeyInput.CONTROLC]):
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
    with question_patcher(responses=inputs):
        assert select_list_multiple("Select options:", options) == expected


def test_select_list_multiple_with_default():
    with question_patcher(responses=[""]):
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
    with question_patcher(responses=inputs):
        assert select_list("Select an option:", options, default=default) == expected


def test_select_list_many_options_supports_search():
    with question_patcher(responses=["q", ""]):
        assert select_list("Choose a letter", list("abcdefghijklmnopqrstuvwxyz")) == "q"


def test_select_list_supports_shortcut_on_shorter_lists():
    with question_patcher(responses=["3"]):
        assert select_list("Choose a number", ["1", "2", "3"]) == "3"
    with question_patcher(responses=[f"{SEARCH_ENABLED_AFTER_CHOICES}"]):
        assert (
            select_list(
                "Choose a number",
                [str(i) for i in range(1, SEARCH_ENABLED_AFTER_CHOICES + 1)],
            )
            == f"{SEARCH_ENABLED_AFTER_CHOICES}"
        )


def test_explicit_select_options():
    with question_patcher(responses=["j"]):
        assert (
            select_list(
                "Choose a letter",
                list("abcdefghijklmnopqrstuvwxyz"),
                options=SelectOptions(use_jk_keys=True),
            )
            == "b"
        )


def test_select_dict():
    with question_patcher(responses=["", "Option 2"]):
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
        with question_patcher(responses=[]):
            select_list("Select an option:", ["Option 1", "Option 2"])


def test_return_default_if_not_interactive_should_raise_error_when_not_interactive():
    with pytest.raises(
        ValueError,
        match="Function called in non-interactive shell, but no default value provided",
    ):
        text("Are you sure?")


def test_select_list_multiple_choices_one_selection():
    choices = [
        ChoiceTyped(name="Option 1", value=1),
        ChoiceTyped(name="Option 2", value=2),
    ]
    with question_patcher(responses=[" "]):
        assert select_list_multiple_choices("Select options:", choices) == [1]


def test_select_list_multiple_choices_two_selections():
    choices = [
        ChoiceTyped(name="Option 1", value=1, description="First option"),
        ChoiceTyped(name="Option 2", value=2, description="Second option"),
    ]
    with question_patcher(responses=[f" {KeyInput.DOWN} "]):
        assert select_list_multiple_choices("Select options:", choices) == [1, 2]


def test_select_list_typed():
    choices = [
        ChoiceTyped(name="Option 1", value=1, description="First option"),
        ChoiceTyped(name="Option 2", value=2, description="Second option"),
    ]
    with question_patcher(responses=[""]):
        assert select_list_choice("Select an option", choices) == 1


@pytest.mark.asyncio()
async def test_confirm_async():
    with question_patcher(responses=[""]):
        assert confirm("Confirm from async", default=True)


def test_new_handler_choice():
    new_handler = NewHandlerChoice(int, new_prompt="choose different value")
    with question_patcher(responses=[KeyInput.CONTROLC, "3"]):
        choice = select_list_choice(
            "select me",
            [ChoiceTyped(name="c1", value=1), ChoiceTyped(name="c2", value=2)],
            options=SelectOptions(new_handler_choice=new_handler),
        )
    assert choice == 3


def test_new_handler_choice_multiple():
    new_handler = NewHandlerChoice(int, new_prompt="choose different value")
    with question_patcher(responses=[KeyInput.CONTROLC, "3", ""]):
        choice = select_list_multiple_choices(
            "select me",
            [ChoiceTyped(name="c1", value=1), ChoiceTyped(name="c2", value=2)],
            options=SelectOptions(new_handler_choice=new_handler),
        )
    assert choice == [3]


def test_new_handler_choice_multiple_with_extra():
    new_handler = NewHandlerChoice(int, new_prompt="choose different value")
    with question_patcher(responses=[KeyInput.CONTROLC, "3", f"{KeyInput.DOWN} "]):
        choice = select_list_multiple_choices(
            "select me",
            [ChoiceTyped(name="c1", value=1), ChoiceTyped(name="c2", value=2)],
            options=SelectOptions(new_handler_choice=new_handler),
        )
    assert choice == [3, 1]


def test_prompt_match_exact():
    match = PromptMatch(exact="exact", response="exact")
    assert match("exact")
    assert not match("not exact")


def test_prompt_match_substring():
    match = PromptMatch(substring="sub", response="")
    assert match("this is a substring match")
    assert not match("no match here")


def test_prompt_match_once_only():
    match = PromptMatch(substring="once", max_matches=1, response="")
    assert match("this will match once")
    match.next_response()
    assert not match("this will match once")


def test_prompt_match_twiche():
    match = PromptMatch(substring="once", max_matches=2, responses=["1", "2"])
    assert match("this will match once")
    match.next_response()
    assert match("this will match once")
    match.next_response()
    assert not match("this will match once")


def test_prompt_dynamic_match():
    prompt_text = "my prompt"
    response_expected = "hello world!"
    with question_patcher(
        dynamic_responses=[PromptMatch(exact=prompt_text, response=response_expected)]
    ):
        response = text(prompt_text)
    assert response_expected == response


def test_no_dynamic_match():
    prompt_text = "my prompt"
    with pytest.raises(
        ValueError,
        match="Not enough responses provided. Expected 0, got 1 questions. Last prompt: 'my prompt'",
    ):
        with question_patcher():
            text(prompt_text)


def test_raise_on_question():
    with pytest.raises(RaiseOnQuestionError, match="Question asked: 'hello error'"):
        with raise_on_question():
            text("hello error")
