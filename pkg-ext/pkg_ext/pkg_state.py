from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from model_lib.model_base import Entity
from pydantic import DirectoryPath, Field

from pkg_ext.changelog.actions import (
    ChangelogAction,
    DeleteAction,
    DeprecatedAction,
    ExperimentalAction,
    FixAction,
    GAAction,
    GroupModuleAction,
    KeepPrivateAction,
    MakePublicAction,
    RenameAction,
)
from pkg_ext.config import Stability
from pkg_ext.errors import RefSymbolNotInCodeError
from pkg_ext.models.code_state import PkgCodeState
from pkg_ext.models.groups import PublicGroups
from pkg_ext.models.py_symbols import RefSymbol
from pkg_ext.models.ref_state import RefState, RefStateType, RefStateWithSymbol
from pkg_ext.models.types import qualified_name


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
    group_stability: dict[str, Stability] = Field(
        default_factory=dict,
        description="Group name to stability level. Absence means GA.",
    )
    symbol_stability: dict[str, Stability] = Field(
        default_factory=dict,
        description="Key = {group}.{symbol}, value = stability level.",
    )
    arg_stability: dict[str, Stability] = Field(
        default_factory=dict,
        description="Key = {group}.{symbol}.{arg}, value = stability level.",
    )

    def code_ref(
        self, code_state: PkgCodeState, group: str, name: str
    ) -> RefSymbol | None:
        key = qualified_name(group, name)
        if state := self.refs.get(key):
            if state.exist_in_code:
                with suppress(RefSymbolNotInCodeError):
                    return code_state.ref_symbol(name)
        return None

    def sha_processed(self, sha: str) -> bool:
        return sha in self.ignored_shas or sha in self.included_shas

    def current_state(self, group: str, ref_name: str) -> RefState:
        key = qualified_name(group, ref_name)
        if state := self.refs.get(key):
            return state
        self.refs[key] = state = RefState(name=ref_name)
        return state

    def update_state(self, action: ChangelogAction) -> None:
        match action:
            case MakePublicAction(name=name, group=group):
                state = self.current_state(group, name)
                state.type = RefStateType.EXPOSED
            case KeepPrivateAction(name=name):
                # KeepPrivate uses full_path for identification, no group needed
                key = name  # Use name directly as key for hidden refs
                if state := self.refs.get(key):
                    state.type = RefStateType.HIDDEN
                else:
                    self.refs[key] = RefState(name=name, type=RefStateType.HIDDEN)
            case DeleteAction(name=name, group=group):
                state = self.current_state(group, name)
                state.type = RefStateType.DELETED
            case RenameAction(name=name, group=group, old_name=old_name):
                state = self.current_state(group, name)
                old_state = self.current_state(group, old_name)
                old_state.type = RefStateType.DELETED
                state.type = RefStateType.EXPOSED
            case GroupModuleAction(name=group_name, module_path=module_path):
                self.groups.add_module(group_name, module_path)
            case FixAction(short_sha=sha, ignored=ignored):
                shas = self.ignored_shas if ignored else self.included_shas
                shas.add(sha)
            case ExperimentalAction() | GAAction() | DeprecatedAction():
                self._update_stability(action)

    def _stability_from_action(self, action: ChangelogAction) -> Stability:
        match action:
            case ExperimentalAction():
                return Stability.experimental
            case GAAction():
                return Stability.ga
            case DeprecatedAction():
                return Stability.deprecated
        raise ValueError(f"Unknown stability action: {action}")

    def _update_stability(
        self, action: ExperimentalAction | GAAction | DeprecatedAction
    ) -> None:
        stability = self._stability_from_action(action)
        target = str(action.target)
        match target:
            case "group":
                self.group_stability[action.name] = stability
            case "symbol":
                key = f"{action.group}.{action.name}"
                self.symbol_stability[key] = stability
            case "arg":
                key = f"{action.parent}.{action.name}"
                self.arg_stability[key] = stability

    def get_group_stability(self, group: str) -> Stability:
        return self.group_stability.get(group, Stability.ga)

    def get_symbol_stability(self, group: str, symbol: str) -> Stability:
        key = f"{group}.{symbol}"
        if key in self.symbol_stability:
            return self.symbol_stability[key]
        return self.get_group_stability(group)

    def get_arg_stability(self, group: str, symbol: str, arg: str) -> Stability:
        key = f"{group}.{symbol}.{arg}"
        if key in self.arg_stability:
            return self.arg_stability[key]
        return self.get_symbol_stability(group, symbol)

    def is_group_ga(self, group: str) -> bool:
        return self.get_group_stability(group) == Stability.ga

    def _refs_by_short_name(self) -> dict[str, list[RefState]]:
        """Group refs by short name for lookups when group is unknown."""
        from collections import defaultdict

        result: dict[str, list[RefState]] = defaultdict(list)
        for state in self.refs.values():
            result[state.name].append(state)
        return result

    def has_decision(self, ref_name: str) -> bool:
        """Check if any decision (expose/hide) has been made for this short name."""
        return any(
            state.type != RefStateType.UNSET
            for state in self._refs_by_short_name().get(ref_name, [])
        )

    def removed_refs(self, code: PkgCodeState) -> list[tuple[str, RefState]]:
        """Returns list of (group, RefState) for removed refs."""
        named_refs = code.named_refs
        result: list[tuple[str, RefState]] = []
        for key, state in self.refs.items():
            if state.type not in {RefStateType.EXPOSED, RefStateType.DEPRECATED}:
                continue
            if state.name in named_refs:
                continue
            # Extract group from qualified_name key
            group = key.rsplit(".", 1)[0] if "." in key else ""
            result.append((group, state))
        return result

    def added_refs(
        self, active_refs: dict[str, RefStateWithSymbol]
    ) -> dict[str, RefStateWithSymbol]:
        return {
            ref_name: ref_symbol
            for ref_name, ref_symbol in active_refs.items()
            if not self.has_decision(ref_name)
        }

    def add_changelog_actions(self, actions: list[ChangelogAction]) -> None:
        assert actions, "must add at least one action"
        for action in actions:
            self.update_state(action)

    def is_exposed(self, group: str, ref_name: str) -> bool:
        key = qualified_name(group, ref_name)
        if state := self.refs.get(key):
            return state.type in {RefStateType.EXPOSED, RefStateType.DEPRECATED}
        return False

    def exposed_refs(
        self, group: str, active_refs: dict[str, RefStateWithSymbol]
    ) -> dict[str, RefSymbol]:
        return {
            name: state.symbol
            for name, state in active_refs.items()
            if self.is_exposed(group, name)
        }

    def is_pkg_relative(self, rel_path: str) -> bool:
        pkg_rel_path = self.pkg_path.relative_to(self.repo_root)
        return rel_path.startswith(str(pkg_rel_path))

    def full_path(self, rel_path_repo: str) -> Path:
        return self.repo_root / rel_path_repo
