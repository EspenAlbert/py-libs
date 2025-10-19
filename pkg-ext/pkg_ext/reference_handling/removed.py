import logging

from ask_shell._internal.rich_progress import new_task

from pkg_ext.changelog import ChangelogActionType, OldNameNewNameChangelog
from pkg_ext.interactive import (
    confirm_create_alias,
    confirm_delete,
    select_multiple_ref_state,
    select_ref,
)
from pkg_ext.models import (
    RefState,
    RefStateWithSymbol,
    pkg_ctx,
)

logger = logging.getLogger(__name__)


def process_reference_renames(
    active_refs: dict[str, RefStateWithSymbol],
    renames: list[RefState],
    task: new_task,
    ctx: pkg_ctx,
) -> set[RefState]:
    renamed_refs = set()
    used_active: set[str] = set()
    for ref in renames:
        rename_choices = [
            state for name, state in active_refs.items() if name not in used_active
        ]
        new_ref = select_ref(
            f"Select new name for the reference {ref.name} with type: {ref.type}",
            rename_choices,
        )
        new_name = new_ref.name
        used_active.add(new_name)
        if confirm_create_alias(ref, new_ref):
            raise NotImplementedError("Alias creation is not implemented yet")
            # Any DELETE is a breaking change? Or also add that entry?
        ctx.add_action(
            new_name,
            ChangelogActionType.RENAME_AND_DELETE,
            OldNameNewNameChangelog(old_name=ref.name, new_name=new_name),
        )
        renamed_refs.add(ref)
        task.update(advance=1)
    return renamed_refs


def handle_removed_refs(ctx: pkg_ctx) -> None:
    tool_state = ctx.tool_state
    code_state = ctx.code_state
    removed_refs = tool_state.removed_refs(code_state)
    if not removed_refs:
        logger.info("No removed references found in the package")
        return
    if renames := select_multiple_ref_state(
        "Select references that have been renamed (if any):", removed_refs
    ):
        with new_task(
            "Renaming references", total=len(renames), log_updates=True
        ) as task:
            renamed_refs = process_reference_renames(
                code_state.named_refs, renames, task, ctx
            )
            for ref in renamed_refs:
                removed_refs.remove(ref)
    delete_names = ", ".join(ref.name for ref in removed_refs)
    if confirm_delete(removed_refs):
        for ref in removed_refs:
            ctx.add_action(ref.name, ChangelogActionType.DELETE)
    else:
        assert False, f"Old references {delete_names} were not confirmed for deletion"
