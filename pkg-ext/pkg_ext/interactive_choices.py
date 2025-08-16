from ask_shell._internal.interactive import (
    ChoiceTyped,
    NewHandlerChoice,
    SelectOptions,
    confirm,
    select_list_choice,
)

from pkg_ext.errors import NoPublicGroupMatch
from pkg_ext.models import (
    PublicGroup,
    PublicGroups,
    RefState,
    RefStateWithSymbol,
    RefSymbol,
    SymbolType,
    ref_id,
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
    groups: PublicGroups, rel_path: str, symbol_name: str
) -> SelectOptions[PublicGroup]:
    def new_public_group(name: str) -> PublicGroup:
        group = groups.add_group(PublicGroup(name=name))
        ref = RefSymbol(name=symbol_name, type=SymbolType.UNKNOWN, rel_path=rel_path)
        groups.add_ref(ref, name)
        return group

    return SelectOptions(
        new_handler_choice=NewHandlerChoice(
            new_public_group, "enter name of new public group"
        )
    )


def select_group(groups: PublicGroups, rel_path: str, symbol_name: str) -> PublicGroup:
    try:
        group = groups.matching_group(symbol_name, rel_path)
        if confirm(
            f"group {group.name} is ok for {ref_id(rel_path, symbol_name)}?",
            default=True,
        ):
            return group
    except NoPublicGroupMatch:
        pass
    choices = as_choices(groups)
    return select_list_choice(
        "Choose public API group name",
        choices,
        options=new_public_group_constructor(groups, rel_path, symbol_name),
    )


def select_groups(groups: PublicGroups, refs: list[RefStateWithSymbol]) -> None:
    raise NotImplementedError


def as_choice(ref: RefSymbol, checked: bool) -> ChoiceTyped:
    test_usages_str = (
        ", ".join(ref.test_usages) if ref.test_usages else "No test usages"
    )
    src_usages_str = ", ".join(ref.src_usages) if ref.src_usages else "No source usages"
    return ChoiceTyped(
        name=f"{ref.name} {ref.type} {len(ref.src_usages)} src usages {len(ref.test_usages)} test usages",
        value=ref.name,
        description=f"{ref.docstring}\nSource usages: {src_usages_str}\nTest usages: {test_usages_str}",
        checked=checked,
    )


def select_multiple_refs(
    prompt_text: str, refs: list[RefStateWithSymbol]
) -> list[RefStateWithSymbol]:
    choices = {state.name: as_choice(state.symbol, checked=False) for state in refs}
    assert choices, "todo"
    assert prompt_text, "todo"
    raise NotImplementedError()


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
