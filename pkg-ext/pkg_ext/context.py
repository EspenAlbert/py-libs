from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, TypeAlias

from pkg_ext.changelog import (
    ChangelogAction,
    ChangelogActionBase,
    FixAction,
    MakePublicAction,
    changelog_filepath,
    default_changelog_path,
    dump_changelog_actions,
    parse_changelog_file_path,
)
from pkg_ext.errors import NoPublicGroupMatch
from pkg_ext.git_usage import GitChanges
from pkg_ext.models.code_state import PkgCodeState
from pkg_ext.models.groups import PublicGroup
from pkg_ext.models.py_symbols import RefSymbol
from pkg_ext.pkg_state import PkgExtState
from pkg_ext.settings import PkgSettings

RefAddCallback: TypeAlias = Callable[[RefSymbol], ChangelogActionBase | None]


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
    _actions_dumped: bool = True

    @property
    def changelog_path(self) -> Path:
        pr = self.explicit_pr or self.git_changes.current_pr
        return changelog_filepath(self.settings.changelog_dir, pr)

    def __post_init__(self):
        changelog_dir = self.settings.changelog_dir
        path = self.changelog_path
        default_path = default_changelog_path(changelog_dir)
        dump_to_disk = False
        if default_path.exists() and path != default_path:
            self._actions.extend(parse_changelog_file_path(default_path))
            default_path.unlink()
            dump_to_disk = True
        if path.exists():
            self._actions.extend(parse_changelog_file_path(path))
        if dump_to_disk:
            dump_changelog_actions(path, self._actions)

    def add_versions(self, old_version: str, new_version: str):
        self.run_state.old_version = old_version
        self.run_state.new_version = new_version

    def add_changelog_action(
        self, action: ChangelogActionBase
    ) -> list[ChangelogActionBase]:
        actions: list[ChangelogActionBase] = [action]
        if isinstance(action, MakePublicAction):
            ref = self.code_state.ref_symbol(action.name)
            for call in self.ref_add_callback:
                if extra_action := call(ref):
                    actions.insert(0, extra_action)
        self._actions.extend(actions)  # type: ignore[arg-type]
        self.tool_state.add_changelog_actions(actions)  # type: ignore[arg-type]
        return actions

    def pr_changelog_actions(self) -> list[ChangelogAction]:
        if self._actions_dumped:
            return parse_changelog_file_path(self.changelog_path)
        return self._actions

    def action_group(self, action: ChangelogAction) -> PublicGroup:
        match action:
            case MakePublicAction(name=name):
                if code_ref := self.tool_state.code_ref(self.code_state, name):
                    return self.tool_state.groups.matching_group(code_ref)
            case FixAction(name=group_name):
                return self.tool_state.groups.get_or_create_group(group_name)
        raise NoPublicGroupMatch()

    def __enter__(self) -> pkg_ctx:
        self._actions_dumped = False
        return self

    def __exit__(self, *_):
        self._actions_dumped = True
        if actions := self._actions:
            dump_changelog_actions(self.changelog_path, actions)
