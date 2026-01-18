import logging
from pathlib import Path

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

from pkg_ext.changelog import KeepPrivateAction
from pkg_ext.models import (
    PublicGroup,
    PublicGroups,
    RefState,
    RefStateWithSymbol,
    RefSymbol,
)

logger = logging.getLogger(__name__)


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


SKIPPED = "SKIPPED"
_SKIP_CHOICE: ChoiceTyped[str] = ChoiceTyped(
    name="[skip]", value=SKIPPED, description="Skip this commit"
)


def select_group_name_or_skip(
    prompt_text: str, groups: PublicGroups, default: str = ""
) -> PublicGroup | str:
    choices: list[ChoiceTyped[PublicGroup | str]] = [_SKIP_CHOICE] + as_choices(
        groups, default
    )  # type: ignore
    return select_list_choice(prompt_text, choices)


def has_group_conflict(pkg_path: Path, group_name: str) -> bool:
    """Check if group name conflicts with existing source file."""
    return (pkg_path / f"{group_name}.py").exists()


def select_group(groups: PublicGroups, ref: RefSymbol, pkg_path: Path) -> PublicGroup:
    while True:
        choices = as_choices(groups)
        group = select_list_choice(
            f"Choose public API group name for {ref.local_id}",
            choices,
            options=new_public_group_constructor(groups, ref),
        )
        if not group.is_root and has_group_conflict(pkg_path, group.name):
            logger.warning(
                f"Group '{group.name}' conflicts with source file {pkg_path / f'{group.name}.py'}"
            )
            continue
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


PromotableEntry = tuple[KeepPrivateAction | None, RefSymbol]


def _as_choice_promotable(entry: PromotableEntry) -> ChoiceTyped[PromotableEntry]:
    private, ref = entry
    docstring = ref.docstring[:80] + "..." if len(ref.docstring) > 80 else ref.docstring
    location = private.full_path if private else ref.local_id
    label = "[private]" if private else "[new]"
    return ChoiceTyped(
        name=f"{ref.name} {label} ({location})",
        value=entry,
        description=docstring or "No docstring",
        checked=False,
    )


def select_private_symbols(entries: list[PromotableEntry]) -> list[PromotableEntry]:
    choices = [_as_choice_promotable(e) for e in entries]
    return select_list_multiple_choices(
        "Select symbols to promote to public API:", choices
    )


__all__ = [
    "CommitFixAction",
    "confirm_create_alias",
    "confirm_delete",
    "select_commit_fix",
    "select_commit_rephrased",
    "select_group",
    "select_group_name",
    "select_group_name_or_skip",
    "select_multiple_ref_state",
    "select_multiple_refs",
    "select_private_symbols",
    "select_ref",
]
