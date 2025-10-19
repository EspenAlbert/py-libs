from ask_shell._internal.interactive import (
    ChoiceTyped,
    NewHandlerChoice,
    SelectOptions,
    confirm,
    select_dict,
    select_list_choice,
    select_list_multiple_choices,
    text,
)
from zero_3rdparty.enum_utils import StrEnum

from pkg_ext.changelog import (
    ChangelogAction,
    ChangelogActionType,
    GroupModulePathChangelog,
)
from pkg_ext.errors import NoPublicGroupMatch
from pkg_ext.models import (
    PublicGroup,
    PublicGroups,
    RefAddCallback,
    RefState,
    RefStateWithSymbol,
    RefSymbol,
)


def as_choices(
    groups: PublicGroups, default: str = ""
) -> list[ChoiceTyped[PublicGroup]]:
    return [
        ChoiceTyped(
            name=group.name,
            value=group,
            checked=group.name == default,
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


class CommitFixAction(StrEnum):
    INCLUDE = "include"
    EXCLUDE = "exclude"
    REPHRASE = "rephrase"


def select_commit_fix(prompt_text: str) -> CommitFixAction:
    return select_dict(
        prompt_text,
        {option: option for option in list(CommitFixAction)},
        default=CommitFixAction.INCLUDE,
    )


def select_commit_rephrased(commit_message: str) -> str:
    return text("rephrase commit message", default=commit_message)


def select_group_name(
    prompt_text: str, groups: PublicGroups, default: str = ""
) -> PublicGroup:
    choices = as_choices(groups, default)
    return select_list_choice(prompt_text, choices)


def select_group(groups: PublicGroups, ref: RefSymbol) -> PublicGroup:
    choices = as_choices(groups)
    group = select_list_choice(
        f"Choose public API group name for {ref.local_id}",
        choices,
        options=new_public_group_constructor(groups, ref),
    )
    return groups.add_ref(ref, group.name)


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


def on_new_ref(groups: PublicGroups) -> RefAddCallback:
    def on_ref(ref: RefSymbol) -> ChangelogAction | None:
        try:
            found_group = groups.matching_group(ref)
            groups.add_ref(ref, found_group.name)
        except NoPublicGroupMatch:
            new_group = select_group(groups, ref)
            return ChangelogAction(
                name=new_group.name,
                type=ChangelogActionType.GROUP_MODULE,
                details=GroupModulePathChangelog(module_path=ref.module_path),
            )

    return on_ref


__all__ = [
    "CommitFixAction",
    "confirm_create_alias",
    "confirm_delete",
    "on_new_ref",
    "select_commit_fix",
    "select_commit_rephrased",
    "select_group",
    "select_group_name",
    "select_multiple_ref_state",
    "select_multiple_refs",
    "select_ref",
]
