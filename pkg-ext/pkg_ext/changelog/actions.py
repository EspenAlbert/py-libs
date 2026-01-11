from __future__ import annotations

import logging
from functools import cache, total_ordering
from pathlib import Path
from typing import Annotated, ClassVar, Iterable, Literal, Self, Union

from ask_shell import shell
from model_lib import utc_datetime
from model_lib.model_base import Entity
from model_lib.serialize import dump
from model_lib.serialize.yaml_serialize import parse_yaml_str
from pydantic import Field, TypeAdapter, model_validator
from zero_3rdparty.datetime_utils import utc_now
from zero_3rdparty.enum_utils import StrEnum
from zero_3rdparty.file_utils import ensure_parents_write_text

from pkg_ext.git_usage.state import GitChanges

logger = logging.getLogger(__name__)
ACTION_FILE_SPLIT = "---\n"


class StabilityTarget(StrEnum):
    symbol = "symbol"
    arg = "arg"
    group = "group"


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


def _run_cmd(script: str) -> str | None:
    result = shell.run_and_wait(
        script, allow_non_zero_exit=True, skip_progress_output=True
    )
    return result.stdout.strip() or None if result.exit_code == 0 else None


@cache
def current_user() -> str:
    if username := _run_cmd("gh api user --jq .login"):
        return username
    if name := _run_cmd("git config user.name"):
        return name
    return ChangelogActionBase.DEFAULT_AUTHOR


@total_ordering
class ChangelogActionBase(Entity):
    DEFAULT_AUTHOR: ClassVar[str] = "UNSET"

    name: str = Field("", description="Symbol name or Group name or Release Version")
    ts: utc_datetime = Field(default_factory=utc_now)
    author: str = Field(default_factory=current_user)
    pr: int | None = Field(default=0)

    @property
    def bump_type(self) -> BumpType:
        return BumpType.UNDEFINED

    @property
    def file_content(self) -> str:
        data = self.model_dump(exclude_unset=True, exclude_none=True, exclude={"pr"})
        data.setdefault("ts", self.ts)
        data["type"] = (
            self.type
        )  # ensure type is always included for discriminated union
        return dump(data, format="yaml")

    def __lt__(self, other) -> bool:
        if not isinstance(other, ChangelogActionBase):
            raise TypeError
        return (self.ts, self.name) < (other.ts, other.name)


class MakePublicAction(ChangelogActionBase):
    type: Literal["make_public"] = "make_public"
    details: str = ""

    @property
    def bump_type(self) -> BumpType:
        return BumpType.MINOR


class KeepPrivateAction(ChangelogActionBase):
    type: Literal["keep_private"] = "keep_private"
    full_path: str = ""

    @property
    def bump_type(self) -> BumpType:
        return BumpType.UNDEFINED


class FixAction(ChangelogActionBase):
    type: Literal["fix"] = "fix"
    short_sha: str
    message: str
    changelog_message: str = ""
    rephrased: bool = False
    ignored: bool = False

    @property
    def bump_type(self) -> BumpType:
        return BumpType.PATCH


class DeleteAction(ChangelogActionBase):
    type: Literal["delete"] = "delete"

    @property
    def bump_type(self) -> BumpType:
        return BumpType.MAJOR


class RenameAction(ChangelogActionBase):
    type: Literal["rename"] = "rename"
    old_name: str
    new_name: str

    @property
    def bump_type(self) -> BumpType:
        return BumpType.MAJOR


class BreakingChangeAction(ChangelogActionBase):
    type: Literal["breaking_change"] = "breaking_change"
    details: str

    @property
    def bump_type(self) -> BumpType:
        return BumpType.MAJOR


class AdditionalChangeAction(ChangelogActionBase):
    type: Literal["additional_change"] = "additional_change"
    details: str

    @property
    def bump_type(self) -> BumpType:
        return BumpType.PATCH


class GroupModuleAction(ChangelogActionBase):
    type: Literal["group_module"] = "group_module"
    module_path: str


class ReleaseAction(ChangelogActionBase):
    type: Literal["release"] = "release"
    old_version: str


class StabilityActionMixin(Entity):
    target: StabilityTarget
    parent: str | None = Field(
        default=None,
        description="Parent symbol in format {group}.{symbol_name} when target=arg",
    )

    @model_validator(mode="after")
    def validate_parent(self) -> Self:
        if self.target == StabilityTarget.arg:
            if not self.parent:
                raise ValueError("parent required when target=arg")
            if "." not in self.parent:
                raise ValueError("parent must be {group}.{symbol_name} format")
        return self


class ExperimentalAction(StabilityActionMixin, ChangelogActionBase):
    type: Literal["experimental"] = "experimental"

    @property
    def bump_type(self) -> BumpType:
        return BumpType.PATCH


class GAAction(StabilityActionMixin, ChangelogActionBase):
    type: Literal["ga"] = "ga"

    @property
    def bump_type(self) -> BumpType:
        return BumpType.PATCH


class DeprecatedAction(StabilityActionMixin, ChangelogActionBase):
    type: Literal["deprecated"] = "deprecated"

    @property
    def bump_type(self) -> BumpType:
        return BumpType.PATCH


ChangelogAction = Annotated[
    Union[
        MakePublicAction,
        KeepPrivateAction,
        FixAction,
        DeleteAction,
        RenameAction,
        BreakingChangeAction,
        AdditionalChangeAction,
        GroupModuleAction,
        ReleaseAction,
        ExperimentalAction,
        GAAction,
        DeprecatedAction,
    ],
    Field(discriminator="type"),
]


_changelog_action_adapter: TypeAdapter[ChangelogAction] = TypeAdapter(ChangelogAction)


def parse_changelog_file_path(path: Path) -> list[ChangelogAction]:
    if not path.exists():
        logger.warning(f"no changelog file @ {path}")
        return []
    pr_number = int(path.stem)
    actions = []
    for action_raw in path.read_text().split(ACTION_FILE_SPLIT):
        if not action_raw.strip():
            continue
        raw_data = parse_yaml_str(action_raw)
        raw_data["pr"] = pr_number
        actions.append(_changelog_action_adapter.validate_python(raw_data))
    return actions


def parse_changelog_actions(changelog_dir_path: Path) -> list[ChangelogAction]:
    assert changelog_dir_path.is_dir(), f"expected a directory @ {changelog_dir_path}"
    actions: list[ChangelogAction] = []
    for path in changelog_dir_path.rglob("*.yaml"):
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
    files = sorted(changelog_dir_path.glob("*.yaml"))
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
