from __future__ import annotations

import logging
from functools import total_ordering
from pathlib import Path
from typing import ClassVar, Generic, Iterable, Literal, TypeVar, Union

from model_lib import utc_datetime
from model_lib.model_base import Entity
from model_lib.serialize import dump
from model_lib.serialize.parse import parse_model
from pydantic import Field
from zero_3rdparty.datetime_utils import (
    utc_now,
)
from zero_3rdparty.enum_utils import StrEnum
from zero_3rdparty.file_utils import ensure_parents_write_text

from pkg_ext.git_usage.state import GitChanges

logger = logging.getLogger(__name__)
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

    @classmethod
    def sort_by_bump(cls, actions: Iterable[ChangelogAction]) -> list[ChangelogAction]:
        indexes = {bump: i for i, bump in enumerate(cls)}

        def as_index(action: ChangelogAction) -> int:
            return indexes[action.bump_type]

        return sorted(actions, key=as_index)


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
    DEFAULT_AUTHOR: ClassVar[str] = "UNSET"

    name: str = Field("", description="Symbol name or Group name or Release Version")
    type: ChangelogActionType = Field(
        ...,
        description=f"Action to take with the public reference, one of {list(ChangelogActionType)}",
    )
    ts: utc_datetime = Field(
        default_factory=utc_now, description="Timestamp of the action"
    )

    author: str = Field(
        default_factory=current_user,
        description="Author of the public reference action",
    )
    details: ChangelogDetailsT = Field(
        default=None,
        description="Details of the action, for example details on changes",
    )
    pr: int | None = Field(
        default=0,
        description="Pull request number, set from default branch before releasing after merge.",
    )

    @property
    def file_content(self) -> str:
        ignored_falsy = self.model_dump(
            exclude_unset=True,
            exclude_none=True,
            exclude={"pr"},
        )
        ignored_falsy.setdefault("ts", self.ts)
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
    if not path.exists():
        logger.warning(f"no changelog file @ {path}")
        return []
    pr_number = int(path.stem)
    return [
        parse_model(
            action_raw, t=ChangelogAction, format="yaml", extra_kwargs={"pr": pr_number}
        )
        for action_raw in path.read_text().split(ACTION_FILE_SPLIT)
        if action_raw.strip()
    ]


def parse_changelog_actions(changelog_dir_path: Path) -> list[ChangelogAction]:
    assert changelog_dir_path.is_dir(), (
        f"expected a directory @ {changelog_dir_path} got"
    )
    actions: list[ChangelogAction] = []
    for path in changelog_dir_path.rglob(
        "*.yaml"
    ):  # support reading archived changelog actions
        actions.extend(parse_changelog_file_path(path))
    return sorted(actions)


def changelog_filename(pr_number: int) -> str:
    return f"{pr_number:03d}.yaml"


def changelog_archive_path(changelog_file_path: Path, changelog_dir_name: str) -> Path:
    # sourcery skip: raise-from-previous-error
    try:
        pr_number = int(changelog_file_path.stem)
    except ValueError:
        raise ValueError(
            f"changelog file path is not a number, got: {changelog_file_path.stem}"
        )
    changelog_dir_path = next(
        (
            parent
            for parent in changelog_file_path.parents
            if parent.name == changelog_dir_name
        ),
        None,
    )
    assert changelog_dir_path, (
        f"unable to find parent {changelog_dir_name} for {changelog_file_path}"
    )
    archive_directory_name = pr_number // 1000
    return (
        changelog_dir_path
        / f"{archive_directory_name:03d}"
        / changelog_filename(pr_number)
    )


def archive_old_actions(
    changelog_dir_path: Path, cleanup_trigger: int, keep_count: int
) -> bool:
    """Cleans old entries from the .changelog/ directory returns `true` if cleanup was done."""
    files = sorted(changelog_dir_path.glob("*.yaml"))  # only top level files
    file_count = len(files)
    if file_count < cleanup_trigger:
        return False
    move_count = file_count - keep_count
    logger.warning(f"Will archive {move_count} changelog entries")
    for index in range(move_count):
        file = files[index]
        archive_path = changelog_archive_path(file, changelog_dir_path.name)
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        file.rename(archive_path)
        logger.info(f"moving {file} to {archive_path}")
    return True


def changelog_filepath(changelog_dir: Path, pr_number: int) -> Path:
    return changelog_dir / changelog_filename(pr_number)


def default_changelog_path(changelog_dir: Path) -> Path:
    return changelog_filepath(changelog_dir, GitChanges.DEFAULT_PR_NUMBER)


def dump_changelog_actions(path: Path, actions: list[ChangelogAction]) -> Path:
    assert actions, "no actions to dump"
    yaml_content = ACTION_FILE_SPLIT.join(
        action.file_content for action in sorted(actions)
    )
    ensure_parents_write_text(path, yaml_content)
    return path
