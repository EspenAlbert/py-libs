import logging
from collections import defaultdict
from typing import get_type_hints

from ask_shell._internal._run import run_and_wait
from ask_shell._internal.rich_progress import new_task
from zero_3rdparty.iter_utils import group_by_once

from pkg_ext.changelog import KeepPrivateAction, MakePublicAction
from pkg_ext.cli.options import get_default_editor
from pkg_ext.context import pkg_ctx
from pkg_ext.interactive import select_multiple_refs
from pkg_ext.models import (
    PkgCodeState,
    RefStateWithSymbol,
    RefSymbol,
    SymbolType,
)
from pkg_ext.pkg_state import PkgExtState
from pkg_ext.settings import PkgSettings

logger = logging.getLogger(__name__)


def handle_added_refs_flat(ctx: pkg_ctx) -> None:
    tool_state = ctx.tool_state
    code_state = ctx.code_state
    added_refs = tool_state.added_refs(code_state.named_refs)
    if not added_refs:
        logger.info("No new references found in the package")
        return

    groups = tool_state.groups
    for ref_name, ref_with_symbol in added_refs.items():
        ref = ref_with_symbol.symbol
        group_name = ref.module_path
        groups.add_ref(ref, group_name)
        ctx.add_changelog_action(
            MakePublicAction(name=ref_name, details=f"auto-exposed from {ref.rel_path}")
        )
    logger.info(f"Auto-exposed {len(added_refs)} refs in flat package")


def ensure_function_args_exposed(
    code_state: PkgCodeState, function_refs: list[RefStateWithSymbol]
) -> dict[RefStateWithSymbol, list[RefSymbol]]:
    func_arg_symbols: dict[RefStateWithSymbol, list[RefSymbol]] = defaultdict(list)
    for func_ref in function_refs:
        func = code_state.lookup(func_ref.symbol)
        type_hints = get_type_hints(func)
        for name, type in type_hints.items():
            if local_ref := code_state.as_local_ref(type):
                logger.info(f"auto exposing arg {name} on func {func_ref.name}")
                func_arg_symbols[func_ref].append(local_ref)
    return func_arg_symbols


def make_expose_decisions(
    refs: dict[str, list[RefStateWithSymbol]],
    ctx: pkg_ctx,
    tool_state: PkgExtState,
    code_state: PkgCodeState,
    symbol_type: str,
    settings: PkgSettings,
) -> list[RefStateWithSymbol | RefSymbol]:
    decided_refs: list[RefStateWithSymbol | RefSymbol] = []
    for rel_path, file_states in refs.items():
        if not settings.skip_open_in_editor:
            run_and_wait(f"{get_default_editor()} {tool_state.pkg_path / rel_path}")
        exposed = select_multiple_refs(
            f"Select references of type {symbol_type} to expose from {rel_path} (if any):",
            file_states,
        )
        for ref in exposed:
            ctx.add_changelog_action(
                MakePublicAction(name=ref.name, details=f"created in {rel_path}")
            )
        hidden = [state for state in file_states if state not in exposed]
        for ref in hidden:
            ctx.add_changelog_action(
                KeepPrivateAction(name=ref.name, full_path=ref.symbol.local_id)
            )
        if exposed and symbol_type == SymbolType.FUNCTION:
            args_exposed = ensure_function_args_exposed(code_state, exposed)
            for func_ref, arg_refs in args_exposed.items():
                decided_refs.extend(arg_refs)
                for ref in arg_refs:
                    if tool_state.current_state(ref.name).exist_in_code:
                        continue
                    ctx.add_changelog_action(
                        MakePublicAction(
                            name=ref.name,
                            details=f"exposed in the function {func_ref.symbol.local_id}",
                        )
                    )
    return decided_refs


def handle_added_refs(ctx: pkg_ctx) -> None:
    tool_state = ctx.tool_state
    code_state = ctx.code_state
    added_refs = tool_state.added_refs(code_state.named_refs)
    if not added_refs:
        logger.info("No new references found in the package")
        return

    def group_by_rel_path(state: RefStateWithSymbol) -> str:
        return state.symbol.rel_path

    def decide_refs(refs: list[RefStateWithSymbol | RefSymbol]) -> None:
        for ref in refs:
            added_refs.pop(ref.name, None)

    def sort_by_dep_order(
        rel_path_refs: dict[str, list[RefStateWithSymbol]],
    ) -> dict[str, list[RefStateWithSymbol]]:
        sorted_rel_paths = code_state.sort_rel_paths_by_dependecy_order(
            rel_path_refs.keys(), reverse=True
        )
        new_order = {}
        for rel_path in sorted_rel_paths:
            new_order[rel_path] = rel_path_refs[rel_path]
        return new_order

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
            file_added = group_by_once(relevant_refs, key=group_by_rel_path)
            file_added = sort_by_dep_order(file_added)
            extra_refs_decided = make_expose_decisions(
                file_added, ctx, tool_state, code_state, symbol_type, ctx.settings
            )
            all_refs_decided = relevant_refs + extra_refs_decided
            decide_refs(all_refs_decided)
            task.update(advance=len(all_refs_decided))
    if added_refs:
        remaining_str = "\n".join(str(ref) for ref in added_refs.values())
        logger.info(f"still has {len(added_refs)} remaining:\n{remaining_str}")
