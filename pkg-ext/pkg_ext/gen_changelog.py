from functools import total_ordering
from pathlib import Path
from typing import ClassVar, Literal

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


def current_user() -> str:
    return (
        ChangelogAction.DEFAULT_AUTHOR
    )  # todo: read from git config or environment variable


class OldNameNewName(Entity):
    old_name: str
    new_name: str
    type: Literal["old_name_new_name"] = "old_name_new_name"


ChangelogDetailsT = OldNameNewName | str | None


@total_ordering
class ChangelogAction(Entity):
    name: str = Field(..., description="Symbol name")
    action: ChangelogActionType = Field(
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

    def __lt__(self, other) -> bool:
        if not isinstance(other, ChangelogAction):
            raise TypeError
        return (self.ts, self.name) < (other.ts, other.name)

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


def parse_changelog_action(path: Path) -> list[ChangelogAction]:
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
        actions.extend(parse_changelog_action(path))
    return sorted(actions)


def dump_changelog_action(path: Path, action: ChangelogAction) -> None:
    if not path.exists():
        path.write_text(action.file_content)
        return
    existing_actions = parse_changelog_action(path)
    existing_actions.append(action)
    existing_actions.sort()
    yaml_content = ACTION_FILE_SPLIT.join(
        action.file_content for action in existing_actions
    )
    path.write_text(yaml_content)
