import logging

from ask_shell._internal._run import run_and_wait
from ask_shell._internal.rich_progress import new_task
from zero_3rdparty.iter_utils import (
    group_by_once,
)

from pkg_ext.gen_changelog import (
    ChangelogActionType,
)
from pkg_ext.interactive_choices import (
    select_groups,
    select_multiple_refs,
)
from pkg_ext.models import (
    AddChangelogAction,
    PkgCodeState,
    PkgExtState,
    RefStateWithSymbol,
    SymbolType,
)
from pkg_ext.settings import get_editor

logger = logging.getLogger(__name__)


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
    - arg classes
    - exceptions
    2. classes
    - arg classes
    - exceptions
    - type aliases?
    3. errors (ideally, found from functions/errors)
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
