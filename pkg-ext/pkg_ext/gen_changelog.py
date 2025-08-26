from __future__ import annotations

from functools import total_ordering
from pathlib import Path
from typing import ClassVar, Generic, Iterable, Literal, NamedTuple, TypeVar, Union

from model_lib import utc_datetime
from model_lib.model_base import Entity
from model_lib.serialize import dump
from model_lib.serialize.parse import parse_model
from pydantic import Field
from zero_3rdparty.datetime_utils import (
    date_filename_with_seconds,
    parse_date_filename_with_seconds,
    utc_now,
)
from zero_3rdparty.enum_utils import StrEnum
from zero_3rdparty.file_utils import ensure_parents_write_text

ACTION_FILE_SPLIT = "---\n"


class ChangelogActionType(StrEnum):
    EXPOSE = "expose"
    HIDE = "hide"
    FIX = "fix"
    DEPRECATE = "deprecate"
    DELETE = "delete"
    RENAME_AND_DELETE = "rename_and_delete"
    BREAKING_CHANGE = "breaking_change"  # todo: Possibly support signature changes
    ADDITIONAL_CHANGE = "additional_change"  # todo: Possibly support signature changes
    GROUP_MODULE = "group_module"  # a module_path has been selected for a group
    RELEASE = "release"


class BumpType(StrEnum):
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"
    RC = "release_candidate"
    BETA = "beta"
    ALPHA = "alpha"
    UNDEFINED = "undefined"

    @classmethod
    def max_bump_type(cls, bumps: Iterable[BumpType]) -> BumpType:
        bumps_set = set(bumps)
        return next((t for t in list(cls) if t in bumps_set), BumpType.UNDEFINED)


def current_user() -> str:
    return (
        ChangelogAction.DEFAULT_AUTHOR
    )  # todo: read from git config or environment variable


class OldNameNewNameChangelog(Entity):
    old_name: str
    new_name: str
    type: Literal["old_name_new_name"] = "old_name_new_name"


class GroupModulePathChangelog(Entity):
    module_path: str
    type: Literal["group_module_path"] = "group_module_path"


class CommitFixChangelog(Entity):
    short_sha: str
    message: str
    changelog_message: str = ""
    rephrased: bool = False
    ignored: bool = False
    type: Literal["commit_fix"] = "commit_fix"


class ReleaseChangelog(Entity):
    old_version: str
    type: Literal["release"] = "release"


ChangelogDetailsT = Union[
    CommitFixChangelog,
    GroupModulePathChangelog,
    OldNameNewNameChangelog,
    ReleaseChangelog,
    str,
    None,
]

T = TypeVar("T", bound=ChangelogDetailsT)


@total_ordering
class ChangelogAction(Entity, Generic[T]):
    name: str = Field("", description="Symbol name or Group name or Release Version")
    type: ChangelogActionType = Field(
        ...,
        description=f"Action to take with the public reference, one of {list(ChangelogActionType)}",
    )
    ts: utc_datetime = Field(
        default_factory=utc_now, description="Timestamp of the action"
    )

    DEFAULT_AUTHOR: ClassVar[str] = "UNSET"
    author: str = Field(
        default_factory=current_user,
        description="Author of the public reference action",
    )
    details: ChangelogDetailsT = Field(
        default=None,
        description="Details of the action, for example details on changes",
    )
    pr: str | None = Field(
        default="",
        description="Pull request number, set from default branch before releasing after merge.",
    )

    @property
    def filename(self) -> str:
        """Generate a filename for the changelog action based on its timestamp."""
        return f"{date_filename_with_seconds(self.ts, force_utc=True)}.yaml"

    @property
    def file_content(self) -> str:
        ignored_falsy = self.model_dump(
            exclude_unset=True, exclude_none=True, exclude_defaults=True, exclude={"ts"}
        )
        return dump(ignored_falsy, format="yaml")

    @property
    def bump_type(self) -> BumpType:
        return as_bump_type(self)

    def __lt__(self, other) -> bool:
        if not isinstance(other, ChangelogAction):
            raise TypeError
        return (self.ts, self.name) < (other.ts, other.name)


def as_bump_type(action: ChangelogAction) -> BumpType:
    """Might want ot use fields on the action in the future to determine BumpType therefore we pass action instead of type"""
    match action.type:
        case ChangelogActionType.FIX | ChangelogActionType.ADDITIONAL_CHANGE:
            return BumpType.PATCH
        case ChangelogActionType.EXPOSE:
            return BumpType.MINOR
        case (
            ChangelogActionType.BREAKING_CHANGE | ChangelogActionType.RENAME_AND_DELETE
        ):
            return BumpType.MAJOR
    return BumpType.UNDEFINED


def parse_changelog_file_path(path: Path) -> list[ChangelogAction]:
    ts = parse_date_filename_with_seconds(path.stem)
    return [
        parse_model(
            action_raw,
            t=ChangelogAction,
            extra_kwargs={"ts": ts},
            format="yaml",
        )
        for action_raw in path.read_text().split(ACTION_FILE_SPLIT)
        if action_raw.strip()
    ]


def parse_changelog_actions(changelog_dir_path: Path) -> list[ChangelogAction]:
    actions: list[ChangelogAction] = []
    for path in changelog_dir_path.glob("*.yaml"):
        actions.extend(parse_changelog_file_path(path))
    return sorted(actions)


def dump_changelog_actions(changelog_dir: Path, actions: list[ChangelogAction]) -> Path:
    assert actions, "no actions to dump"
    action = min(actions)
    path = changelog_dir / action.filename
    if path.exists():
        existing_actions = parse_changelog_file_path(path)
        actions.extend(existing_actions)
    yaml_content = ACTION_FILE_SPLIT.join(
        action.file_content for action in sorted(actions)
    )
    ensure_parents_write_text(path, yaml_content)
    return path


class UnreleasedActions(NamedTuple):
    actions: list[ChangelogAction]
    last_release: ChangelogAction[ReleaseChangelog] | None


def unreleased_actions(all_actions: list[ChangelogAction]) -> UnreleasedActions:
    """Ensure you use pkg_ctx.all_changelog_actions if you have made any actions"""
    unreleased_actions = []
    last_release = None
    for action in reversed(all_actions):
        if action.type == ChangelogActionType.RELEASE:
            last_release = action
            break
        unreleased_actions.append(action)
    return UnreleasedActions(unreleased_actions, last_release)
