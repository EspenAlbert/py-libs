from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from model_lib.model_base import Entity
from pydantic import DirectoryPath, Field

from pkg_ext.changelog import (
    ChangelogAction,
    ChangelogActionType,
    CommitFixChangelog,
    GroupModulePathChangelog,
    OldNameNewNameChangelog,
)
from pkg_ext.errors import RefSymbolNotInCodeError

from .code_state import PkgCodeState
from .groups import PublicGroups
from .py_symbols import RefSymbol
from .ref_state import RefState, RefStateType, RefStateWithSymbol


class PkgExtState(Entity):
    repo_root: DirectoryPath
    changelog_dir: DirectoryPath
    pkg_path: DirectoryPath
    refs: dict[str, RefState] = Field(
        default_factory=dict,
        description="Mapping of reference names to their states. Use with caution, inferred by changelog_dir entries.",
    )
    groups: PublicGroups = Field(
        default_factory=PublicGroups,
        description="Use with caution, inferred by changelog_dir entries.",
    )
    ignored_shas: set[str] = Field(
        default_factory=set,
        description="Fix commits not included in the changelog",
    )
    included_shas: set[str] = Field(
        default_factory=set,
        description="Fix commits included in the changelog",
    )

    def code_ref(self, code_state: PkgCodeState, name: str) -> RefSymbol | None:
        if state := self.refs.get(name):
            if state.exist_in_code:
                # can happen if the name from changelog has been removed
                with suppress(RefSymbolNotInCodeError):
                    return code_state.ref_symbol(name)
        return None

    def sha_processed(self, sha: str) -> bool:
        return sha in self.ignored_shas or sha in self.included_shas

    def current_state(self, ref_name: str) -> RefState:
        if state := self.refs.get(ref_name):
            return state
        self.refs[ref_name] = state = RefState(name=ref_name)
        return state

    def update_state(self, action: ChangelogAction) -> None:
        """Update the state of a reference based on a changelog action."""
        match action:
            case ChangelogAction(type=ChangelogActionType.EXPOSE):
                state = self.current_state(action.name)
                state.type = RefStateType.EXPOSED
            case ChangelogAction(type=ChangelogActionType.HIDE):
                state = self.current_state(action.name)
                state.type = RefStateType.HIDDEN
            case ChangelogAction(type=ChangelogActionType.DEPRECATE):
                state = self.current_state(action.name)
                state.type = RefStateType.DEPRECATED
            case ChangelogAction(type=ChangelogActionType.DELETE):
                state = self.current_state(action.name)
                state.type = RefStateType.DELETED
            case ChangelogAction(
                type=ChangelogActionType.RENAME_AND_DELETE,
                details=OldNameNewNameChangelog(old_name=old_name),
            ):
                state = self.current_state(action.name)
                old_state = self.current_state(old_name)
                old_state.type = RefStateType.DELETED
                state.type = RefStateType.EXPOSED
            case ChangelogAction(
                name=group_name,
                type=ChangelogActionType.GROUP_MODULE,
                details=GroupModulePathChangelog(module_path=module_path),
            ):
                self.groups.add_module(group_name, module_path)
            case ChangelogAction(
                type=ChangelogActionType.FIX,
                details=CommitFixChangelog(short_sha=sha, ignored=ignored),
            ):
                shas = self.ignored_shas if ignored else self.included_shas
                shas.add(sha)

    def removed_refs(self, code: PkgCodeState) -> list[RefState]:
        named_refs = code.named_refs
        return [
            state
            for ref_name, state in self.refs.items()
            if state.type in {RefStateType.EXPOSED, RefStateType.DEPRECATED}
            and ref_name not in named_refs
        ]

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

    def add_changelog_actions(self, actions: list[ChangelogAction]) -> None:
        assert actions, "must add at least one action"
        for action in actions:
            self.update_state(action)

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

    def is_pkg_relative(self, rel_path: str) -> bool:
        pkg_rel_path = self.pkg_path.relative_to(self.repo_root)
        return rel_path.startswith(str(pkg_rel_path))

    def full_path(self, rel_path_repo: str) -> Path:
        return self.repo_root / rel_path_repo
