import logging

from ask_shell._internal._run import run_and_wait
from ask_shell._internal.interactive import (
    ChoiceTyped,
    confirm,
    select_list_choice,
    select_list_multiple_choices,
)
from ask_shell._internal.rich_progress import new_task
from zero_3rdparty.iter_utils import (
    flat_map,
    group_by_once,
)

from pkg_ext.gen_changelog import (
    ChangelogAction,
    ChangelogActionType,
    OldNameNewName,
)
from pkg_ext.interactive_choices import select_group
from pkg_ext.models import (
    PkgCodeState,
    PkgExtState,
    PkgSrcFile,
    PkgTestFile,
    RefStateWithSymbol,
    RefSymbol,
)
from pkg_ext.settings import get_editor

logger = logging.getLogger(__name__)


def process_reference_renames(
    pkg_state: PkgExtState,
    active_refs: dict[str, RefStateWithSymbol],
    renames: list[str],
    task: new_task,
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
        pkg_state.add_action(
            ChangelogAction(
                name=new_state,
                action=ChangelogActionType.RENAME_AND_DELETE,
                details=OldNameNewName(old_name=ref_name, new_name=new_state),
            )
        )
        renamed_refs.add(ref_name)
        task.update(advance=1)
    return renamed_refs


def handle_removed_refs(tool_state: PkgExtState, code_state: PkgCodeState) -> None:
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
                tool_state, code_state.named_refs, renames, task
            )
            for ref_name in renamed_refs:
                removed_refs.pop(ref_name, None)
    assert confirm(
        "Confirm deleting remaining refs: " + ", ".join(removed_refs.keys()),
    ), (
        f"Old references {', '.join(removed_refs.keys())} were not confirmed for deletion"
    )
    for ref_name, reason in removed_refs.items():
        tool_state.add_action(
            ChangelogAction(
                name=ref_name,
                action=ChangelogActionType.DELETE,
                details=reason,
            )
        )


def handle_added_refs(
    tool_state: PkgExtState,
    code_state: PkgCodeState,
) -> None:
    added_refs = tool_state.added_refs(code_state.named_refs)
    if not added_refs:
        logger.info("No new references found in the package")
        return

    def group_by_module_path(state: RefStateWithSymbol) -> str:
        return state.symbol.rel_path

    file_added_refs = group_by_once(added_refs.values(), key=group_by_module_path)
    with new_task(
        "New References expose decisions", total=len(file_added_refs), log_updates=True
    ) as task:
        for rel_path, file_states in file_added_refs.items():
            run_and_wait(f"{get_editor()} {tool_state.pkg_path / rel_path}")
            choices = {
                state.name: state.symbol.as_choice(checked=False)
                for state in file_states
            }
            expose_refs = select_list_multiple_choices(
                f"Select references to expose from {rel_path} (if any):",
                choices=list(choices.values()),
                default=[],
            )
            for state in file_states:
                action = (
                    ChangelogActionType.EXPOSE
                    if state.name in expose_refs
                    else ChangelogActionType.HIDE
                )
                tool_state.add_action(
                    ChangelogAction(
                        name=state.name,
                        action=action,
                        details=f"Created in {rel_path}",
                    )
                )
                if action == ChangelogActionType.EXPOSE:
                    select_group(tool_state.groups, rel_path, state.name)

            task.update(advance=1)


def create_refs(
    parsed_files: list[PkgSrcFile | PkgTestFile], pkg_import_name: str
) -> dict[str, RefSymbol]:
    refs = {
        symbol.full_id(pkg_import_name): symbol
        for symbol in flat_map(file.iterate_ref_symbols() for file in parsed_files)
    }
    globals_added: set[str] = set()
    for symbol in list(refs.values()):
        global_import = f"{pkg_import_name}:{symbol.name}"
        globals_added.add(global_import)
        refs[global_import] = symbol

    for file in parsed_files:
        for ref_usage in file.iterate_usage_ids():
            ref = refs.get(ref_usage)
            if not ref:
                if "conftest" in ref_usage and isinstance(file, PkgTestFile):
                    logger.debug(
                        f"Skipping conftest usage {ref_usage} in {file.relative_path}"
                    )
                    continue
                logger.warning(f"Reference {ref_usage} not found in parsed files")
                continue
            match file:
                case PkgTestFile():
                    ref.test_usages.append(file.relative_path)
                case PkgSrcFile():
                    ref.src_usages.append(file.relative_path)
    for global_import in globals_added:
        refs.pop(global_import, None)
    return refs
