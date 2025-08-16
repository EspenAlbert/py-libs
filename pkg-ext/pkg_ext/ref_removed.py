import logging

from ask_shell._internal.interactive import (
    ChoiceTyped,
    confirm,
    select_list_choice,
    select_list_multiple_choices,
)
from ask_shell._internal.rich_progress import new_task

from pkg_ext.gen_changelog import ChangelogActionType, OldNameNewName
from pkg_ext.models import (
    AddChangelogAction,
    PkgCodeState,
    PkgExtState,
    RefStateWithSymbol,
)

logger = logging.getLogger(__name__)


def process_reference_renames(
    active_refs: dict[str, RefStateWithSymbol],
    renames: list[str],
    task: new_task,
    add_changelog: AddChangelogAction,
) -> set[str]:
    renamed_refs = set()
    used_active: set[str] = set()
    for ref_name in renames:
        rename_choices = [
            state.as_choice()
            for name, state in active_refs.items()
            if name not in used_active
        ]
        new_state = select_list_choice(
            f"Select new name for the reference {ref_name}",
            choices=rename_choices,
        )
        if confirm(
            f"Rename {ref_name} to {new_state}, should we create an alias to avoid a breaking change?",
            default=False,
        ):
            raise NotImplementedError("Alias creation is not implemented yet")
            # Any DELETE is a breaking change? Or also add that entry?
        add_changelog(
            new_state,
            ChangelogActionType.RENAME_AND_DELETE,
            OldNameNewName(old_name=ref_name, new_name=new_state),
        )
        renamed_refs.add(ref_name)
        task.update(advance=1)
    return renamed_refs


def handle_removed_refs(
    tool_state: PkgExtState, code_state: PkgCodeState, add_changelog: AddChangelogAction
) -> None:
    removed_refs = tool_state.removed_refs(code_state)
    if not removed_refs:
        logger.info("No removed references found in the package")
        return
    if renames := select_list_multiple_choices(
        "Select references that have been renamed (if any):",
        choices=ChoiceTyped.from_descriptions(removed_refs),
    ):
        with new_task(
            "Renaming references", total=len(renames), log_updates=True
        ) as task:
            renamed_refs = process_reference_renames(
                code_state.named_refs, renames, task, add_changelog
            )
            for ref_name in renamed_refs:
                removed_refs.pop(ref_name, None)
    assert confirm(
        "Confirm deleting remaining refs: " + ", ".join(removed_refs.keys()),
    ), (
        f"Old references {', '.join(removed_refs.keys())} were not confirmed for deletion"
    )
    for ref_name, reason in removed_refs.items():
        add_changelog(ref_name, ChangelogActionType.DELETE, details=reason)
