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
    ChangelogActionType,
    OldNameNewName,
)
from pkg_ext.interactive_choices import (
    select_groups,
    select_multiple_refs,
)
from pkg_ext.models import (
    AddChangelogAction,
    PkgCodeState,
    PkgExtState,
    PkgSrcFile,
    PkgTestFile,
    RefStateWithSymbol,
    RefSymbol,
    SymbolType,
)
from pkg_ext.settings import get_editor

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


def ensure_function_args_exposed(
    code_state: PkgCodeState, function_refs: list[RefStateWithSymbol]
) -> dict[RefStateWithSymbol, list[RefStateWithSymbol]]:
    raise NotImplementedError


def make_expose_decisions(
    refs: dict[str, list[RefStateWithSymbol]],
    add_changelog: AddChangelogAction,
    tool_state: PkgExtState,
    code_state: PkgCodeState,
    symbol_type: str,
) -> list[RefStateWithSymbol]:
    decided_refs: list[RefStateWithSymbol] = []
    for rel_path, file_states in refs.items():
        run_and_wait(f"{get_editor()} {tool_state.pkg_path / rel_path}")
        exposed = select_multiple_refs(
            f"Select references of type {symbol_type} to expose from {rel_path} (if any):",
            file_states,
        )
        for ref in exposed:
            add_changelog(
                ref.name, ChangelogActionType.EXPOSE, details=f"created in {rel_path}"
            )
        hidden = [state for state in file_states if state not in exposed]
        for ref in hidden:
            add_changelog(
                ref.name, ChangelogActionType.HIDE, details=f"created in {rel_path}"
            )
        if exposed:
            select_groups(tool_state.groups, exposed)
            if symbol_type == SymbolType.FUNCTION:
                args_exposed = ensure_function_args_exposed(code_state, exposed)
                for func_ref, arg_refs in args_exposed.items():
                    decided_refs.extend(arg_refs)  # avoid asking again
                    for ref in arg_refs:
                        add_changelog(
                            ref.name,
                            ChangelogActionType.EXPOSE,
                            details=f"exposed in the function {func_ref.symbol.local_id}",
                        )
    return decided_refs


def handle_added_refs(
    tool_state: PkgExtState,
    code_state: PkgCodeState,
    add_changelog: AddChangelogAction,
) -> None:
    """
    # Processing Order
    1. functions
    2. function arg classes
    3. errors
    4. constants?
    5. other types?

    # Rules
    1. Any argument in a function must have all its type hints exposed too, unless the argument name starts with "_"
    2. Any errors raised by the function must also be exposed

    """
    added_refs = tool_state.added_refs(code_state.named_refs)
    if not added_refs:
        logger.info("No new references found in the package")
        return

    def group_by_module_path(state: RefStateWithSymbol) -> str:
        return state.symbol.rel_path

    def decide_refs(refs: list[RefStateWithSymbol]) -> None:
        for ref in refs:
            added_refs.pop(ref.name, None)

    with new_task(
        "New References expose/hide decisions",
        total=len(added_refs),
        log_updates=True,
    ) as task:
        for symbol_type in [
            SymbolType.FUNCTION,
            SymbolType.CLASS,
            SymbolType.EXCEPTION,
        ]:
            relevant_refs = [
                ref for ref in added_refs.values() if ref.symbol.type == symbol_type
            ]
            if not relevant_refs:
                continue
            file_added = group_by_once(relevant_refs, key=group_by_module_path)
            extra_refs_decided = make_expose_decisions(
                file_added, add_changelog, tool_state, code_state, symbol_type
            )
            all_refs_decided = relevant_refs + extra_refs_decided
            decide_refs(all_refs_decided)
            task.update(advance=len(all_refs_decided))
    if added_refs:
        remaining_str = "\n".join(str(ref) for ref in added_refs.values())
        logger.info(f"still has {len(added_refs)} remaining:\n{remaining_str}")


def parse_code_symbols(
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
