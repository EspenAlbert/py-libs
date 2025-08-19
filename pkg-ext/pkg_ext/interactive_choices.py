import contextlib

from ask_shell._internal.interactive import (
    ChoiceTyped,
    NewHandlerChoice,
    SelectOptions,
    confirm,
    select_list_choice,
    select_list_multiple_choices,
)

from pkg_ext.errors import NoPublicGroupMatch
from pkg_ext.models import (
    PublicGroup,
    PublicGroups,
    RefState,
    RefStateWithSymbol,
    RefSymbol,
)


def as_choices(groups: PublicGroups) -> list[ChoiceTyped[PublicGroup]]:
    return [
        ChoiceTyped(
            name=group.name,
            value=group,
            description="Don't belong to a group, rather at top level"
            if group.is_root
            else "",
        )
        for group in groups.groups
    ]


def new_public_group_constructor(
    groups: PublicGroups, ref: RefSymbol
) -> SelectOptions[PublicGroup]:
    def new_public_group(name: str) -> PublicGroup:
        return groups.add_ref(ref, name)

    return SelectOptions(
        new_handler_choice=NewHandlerChoice(
            new_public_group, "enter name of new public group"
        )
    )


def select_group(groups: PublicGroups, ref: RefSymbol) -> PublicGroup:
    with contextlib.suppress(NoPublicGroupMatch):
        group = groups.matching_group(ref)
        return groups.add_ref(ref, group.name)
    choices = as_choices(groups)
    group = select_list_choice(
        "Choose public API group name",
        choices,
        options=new_public_group_constructor(groups, ref),
    )
    return groups.add_ref(ref, group.name)


def select_groups(
    groups: PublicGroups,
    refs: list[RefStateWithSymbol | RefSymbol] | list[RefStateWithSymbol],
) -> None:
    for ref in refs:
        if isinstance(ref, RefSymbol):
            select_group(groups, ref)
        else:
            select_group(groups, ref.symbol)


def _as_choice_ref_symbol(ref: RefSymbol, checked: bool) -> ChoiceTyped[RefSymbol]:
    test_usages_str = (
        ", ".join(ref.test_usages) if ref.test_usages else "No test usages"
    )
    src_usages_str = ", ".join(ref.src_usages) if ref.src_usages else "No source usages"
    return ChoiceTyped(
        name=f"{ref.name} {ref.type} {len(ref.src_usages)} src usages {len(ref.test_usages)} test usages",
        value=ref,
        description=f"{ref.docstring}\nSource usages: {src_usages_str}\nTest usages: {test_usages_str}",
        checked=checked,
    )


def _as_choice_ref_state(
    state: RefStateWithSymbol, checked: bool
) -> ChoiceTyped[RefStateWithSymbol]:
    symbol_choice = _as_choice_ref_symbol(state.symbol, checked)
    symbol_choice.value = state  # type: ignore
    return symbol_choice  # type: ignore


def select_multiple_refs(
    prompt_text: str, refs: list[RefStateWithSymbol]
) -> list[RefStateWithSymbol]:
    choices = [_as_choice_ref_state(state, checked=False) for state in refs]
    assert choices, "todo"
    assert prompt_text, "todo"
    return select_list_multiple_choices(prompt_text, choices)


def select_multiple_ref_state(prompt_text: str, refs: list[RefState]) -> list[RefState]:
    raise NotImplementedError


def select_ref(prompt_text: str, refs: list[RefStateWithSymbol]) -> RefStateWithSymbol:
    raise NotImplementedError


def confirm_create_alias(ref: RefState, new_ref: RefStateWithSymbol) -> bool:
    # todo:
    return False


def confirm_delete(refs: list[RefState]) -> bool:
    delete_names = ", ".join(ref.name for ref in refs)
    return confirm(f"Confirm deleting remaining refs: {delete_names}")
