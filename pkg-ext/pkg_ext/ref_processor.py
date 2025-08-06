import logging
from pathlib import Path

from ask_shell._run import run_and_wait
from ask_shell.interactive import (
    ChoiceTyped,
    confirm,
    select_list_choice,
    select_list_multiple_choices,
)
from ask_shell.rich_progress import new_task
from model_lib.model_base import Entity
from pydantic import DirectoryPath, Field
from zero_3rdparty.iter_utils import (
    flat_map,
    group_by_once,
)

from pkg_ext.gen_changelog import (
    ChangelogAction,
    ChangelogActionType,
    OldNameNewName,
    dump_changelog_action,
    parse_changelog_actions,
)
from pkg_ext.models import (
    PkgSrcFile,
    PkgTestFile,
    RefState,
    RefStateType,
    RefStateWithSymbol,
    RefSymbol,
)
from pkg_ext.settings import get_editor

logger = logging.getLogger(__name__)


class PkgRefState(Entity):
    refs: dict[str, RefState] = Field(
        default_factory=dict, description="Mapping of reference names to their states"
    )
    changelog_dir: DirectoryPath
    pkg_path: DirectoryPath

    def current_state(self, ref_name: str) -> RefState:
        if state := self.refs.get(ref_name):
            return state
        self.refs[ref_name] = state = RefState(name=ref_name)
        return state

    def update_state(self, action: ChangelogAction) -> None:
        """Update the state of a reference based on a changelog action."""
        state = self.current_state(action.name)
        match action.action:
            case ChangelogActionType.EXPOSE:
                state.type = RefStateType.EXPOSED
            case ChangelogActionType.HIDE:
                state.type = RefStateType.HIDDEN
            case ChangelogActionType.DEPRECATE:
                state.type = RefStateType.DEPRECATED
            case ChangelogActionType.DELETE:
                state.type = RefStateType.DELETED
            case ChangelogActionType.RENAME_AND_DELETE:
                details = action.details
                if isinstance(details, OldNameNewName):
                    old_state = self.current_state(details.old_name)
                    old_state.type = RefStateType.DELETED
                    state.type = RefStateType.EXPOSED

    def removed_refs(
        self, active_refs: dict[str, RefStateWithSymbol]
    ) -> dict[str, str]:
        return {
            ref_name: f"{state.type.value} -> removed"
            for ref_name, state in self.refs.items()
            if state.type in {RefStateType.EXPOSED, RefStateType.DEPRECATED}
            and ref_name not in active_refs
        }

    def added_refs(
        self, active_refs: dict[str, RefStateWithSymbol]
    ) -> dict[str, RefStateWithSymbol]:
        """Get references that were added to the package."""
        return {
            ref_name: ref_symbol
            for ref_name, ref_symbol in active_refs.items()
            if ref_name not in self.refs
            or (self.refs[ref_name].type == RefStateType.UNSET)
        }

    def add_action(self, action: ChangelogAction) -> None:
        self.update_state(action)
        path = self.changelog_dir / action.filename
        dump_changelog_action(path, action)

    def is_exposed(self, ref_name: str) -> bool:
        return self.current_state(ref_name).type in {
            RefStateType.EXPOSED,
            RefStateType.DEPRECATED,
        }

    def exposed_refs(
        self, active_refs: dict[str, RefStateWithSymbol]
    ) -> dict[str, RefSymbol]:
        return {
            name: state.symbol
            for name, state in active_refs.items()
            if self.is_exposed(name)
        }


def create_ref_state(pkg_path: Path, changelog_dir: Path) -> PkgRefState:
    """Create a mapping of reference names to their states based on changelog actions."""
    actions = parse_changelog_actions(changelog_dir)
    ref_state = PkgRefState(changelog_dir=changelog_dir, pkg_path=pkg_path)
    for action in actions:
        ref_state.update_state(action)
    return ref_state


def named_refs(import_id_refs: dict[str, RefSymbol]) -> dict[str, RefStateWithSymbol]:
    active_refs = group_by_once(import_id_refs.values(), key=lambda ref: ref.name)
    duplicated_refs = [
        f"duplicated refs for {name}: " + ", ".join(str(ref) for ref in duplicated_refs)
        for name, duplicated_refs in active_refs.items()
        if len(duplicated_refs) > 1
    ]
    duplicated_refs_lines = "\n".join(duplicated_refs)
    assert not duplicated_refs, f"Found duplicated references: {duplicated_refs_lines}"
    return {
        ref.name: RefStateWithSymbol(name=ref.name, symbol=ref)
        for ref in import_id_refs.values()
    }


def process_reference_renames(
    pkg_state: PkgRefState,
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


def handle_removed_refs(
    pkg_state: PkgRefState, active_refs: dict[str, RefStateWithSymbol]
) -> None:
    removed_refs = pkg_state.removed_refs(active_refs)
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
                pkg_state, active_refs, renames, task
            )
            for ref_name in renamed_refs:
                removed_refs.pop(ref_name, None)
    assert confirm(
        "Confirm deleting remaining refs: " + ", ".join(removed_refs.keys()),
    ), (
        f"Old references {', '.join(removed_refs.keys())} were not confirmed for deletion"
    )
    for ref_name, reason in removed_refs.items():
        pkg_state.add_action(
            ChangelogAction(
                name=ref_name,
                action=ChangelogActionType.DELETE,
                details=reason,
            )
        )


def handle_added_refs(
    pkg_state: PkgRefState, active_refs: dict[str, RefStateWithSymbol]
) -> None:
    added_refs = pkg_state.added_refs(active_refs)
    if not added_refs:
        logger.info("No new references found in the package")
        return

    def group_by_file(state: RefStateWithSymbol) -> str:
        return state.symbol.rel_path

    file_added_refs = group_by_once(added_refs.values(), key=group_by_file)
    with new_task(
        "New References expose decisions", total=len(file_added_refs), log_updates=True
    ) as task:
        for file_name, file_states in file_added_refs.items():
            run_and_wait(f"{get_editor()} {pkg_state.pkg_path / file_name}")
            choices = {
                state.name: state.symbol.as_choice(checked=False)
                for state in file_states
            }
            expose_refs = select_list_multiple_choices(
                f"Select references to expose from {file_name} (if any):",
                choices=list(choices.values()),
                default=[],
            )
            for state in file_states:
                action = (
                    ChangelogActionType.EXPOSE
                    if state.name in expose_refs
                    else ChangelogActionType.HIDE
                )
                pkg_state.add_action(
                    ChangelogAction(
                        name=state.name,
                        action=action,
                        details=f"Created in {file_name}",
                    )
                )
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
