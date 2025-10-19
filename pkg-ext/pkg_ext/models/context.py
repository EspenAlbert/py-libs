from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, TypeAlias

from pkg_ext.changelog import (
    ChangelogAction,
    ChangelogActionType,
    ChangelogDetailsT,
    changelog_filepath,
    default_changelog_path,
    dump_changelog_actions,
    parse_changelog_actions,
    parse_changelog_file_path,
)
from pkg_ext.errors import NoPublicGroupMatch
from pkg_ext.git_usage import GitChanges
from pkg_ext.settings import PkgSettings

from .code_state import PkgCodeState
from .groups import PublicGroup
from .pkg_state import PkgExtState
from .py_symbols import RefSymbol

RefAddCallback: TypeAlias = Callable[[RefSymbol], ChangelogAction | None]


@dataclass
class RunState:
    old_version: str = ""
    new_version: str = ""

    def current_or_next_version(self, is_bump: bool) -> str:
        return self.new_version if is_bump else self.old_version


@dataclass
class pkg_ctx:
    settings: PkgSettings
    tool_state: PkgExtState
    code_state: PkgCodeState
    git_changes: GitChanges
    ref_add_callback: list[RefAddCallback] = field(default_factory=list)
    run_state: RunState = field(default_factory=RunState)
    explicit_pr: int = 0

    _actions: list[ChangelogAction] = field(default_factory=list)
    _actions_dumped: bool = False

    @property
    def changelog_path(self) -> Path:
        pr = self.explicit_pr or self.git_changes.current_pr
        return changelog_filepath(self.settings.changelog_path, pr)

    def add_versions(self, old_version: str, new_version: str):
        self.run_state.old_version = old_version
        self.run_state.new_version = new_version

    def add_changelog_action(self, action: ChangelogAction) -> list[ChangelogAction]:
        actions = [action]
        name = action.name
        if action.type == ChangelogActionType.EXPOSE:
            ref = self.code_state.ref_symbol(name)
            for call in self.ref_add_callback:
                if extra_action := call(ref):
                    actions.insert(0, extra_action)
        self._actions.extend(actions)
        self.tool_state.add_changelog_actions(actions)
        return actions

    def add_action(
        self,
        name: str,
        type: ChangelogActionType,
        details: ChangelogDetailsT | None = None,
    ) -> list[ChangelogAction]:
        action = ChangelogAction(name=name, type=type, details=details)
        return self.add_changelog_action(action)

    def all_changelog_actions(self) -> list[ChangelogAction]:
        if self._actions_dumped:
            return parse_changelog_actions(self.settings.changelog_path)
        return parse_changelog_actions(self.settings.changelog_path) + self._actions

    def action_group(self, action: ChangelogAction) -> PublicGroup:
        match action:
            case ChangelogAction(name=name, type=ChangelogActionType.EXPOSE):
                if code_ref := self.tool_state.code_ref(self.code_state, name):
                    return self.tool_state.groups.matching_group(code_ref)
            case ChangelogAction(name=group_name, type=ChangelogActionType.FIX):
                return self.tool_state.groups.get_or_create_group(group_name)
        raise NoPublicGroupMatch()

    def unreleased_actions(self) -> list[ChangelogAction]:
        if not self._actions_dumped:
            return self._actions
        actions = parse_changelog_file_path(self.changelog_path)
        if release_action := next(
            (
                action
                for action in actions
                if action.type == ChangelogActionType.RELEASE
            ),
            None,
        ):
            raise ValueError(
                f"Changelog file {self.changelog_path} contains a RELEASE action, cannot get unreleased actions. {release_action.name}"
            )
        return actions

    def __enter__(self) -> pkg_ctx:
        changelog_dir = self.settings.changelog_path
        path = self.changelog_path
        default_path = default_changelog_path(changelog_dir)
        if default_path.exists() and path != default_path:
            self._actions.extend(parse_changelog_actions(default_path))
            default_path.unlink()  # avoid storing actions now that we have a new path
        if path.exists():
            self._actions.extend(parse_changelog_file_path(path))
        return self

    def __exit__(self, *_):
        self._actions_dumped = True
        if actions := self._actions:
            dump_changelog_actions(self.changelog_path, actions)
