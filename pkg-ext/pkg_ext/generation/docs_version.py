"""Version tracking and changelog integration for docs generation."""

from collections.abc import Sequence
from datetime import datetime

from model_lib import Event, fields

from pkg_ext.changelog.actions import (
    AdditionalChangeAction,
    BreakingChangeAction,
    ChangelogAction,
    DeprecatedAction,
    ExperimentalAction,
    FixAction,
    GAAction,
    MakePublicAction,
    ReleaseAction,
    RenameAction,
    StabilityTarget,
)
from pkg_ext.config import Stability

MEANINGFUL_CHANGE_ACTIONS: tuple[type, ...] = (
    FixAction,
    BreakingChangeAction,
    AdditionalChangeAction,
    RenameAction,
    DeprecatedAction,
)

UNRELEASED_VERSION = "unreleased"


class SymbolChange(Event):
    version: str
    description: str
    ts: UtcDatetime


def find_release_version(
    ts: datetime, changelog_actions: Sequence[ChangelogAction]
) -> str | None:
    for action in sorted(changelog_actions):
        if isinstance(action, ReleaseAction) and action.ts > ts:
            return action.name
    return None


def get_symbol_stability(
    symbol_name: str, group_name: str, changelog_actions: Sequence[ChangelogAction]
) -> Stability:
    last_stability: Stability = Stability.ga
    for action in sorted(changelog_actions):
        if isinstance(action, ExperimentalAction):
            if _matches_symbol_or_group(action, symbol_name, group_name):
                last_stability = Stability.experimental
        elif isinstance(action, GAAction):
            if _matches_symbol_or_group(action, symbol_name, group_name):
                last_stability = Stability.ga
        elif isinstance(action, DeprecatedAction):
            if _matches_symbol_or_group(action, symbol_name, group_name):
                last_stability = Stability.deprecated
    return last_stability


def _matches_symbol_or_group(
    action: ExperimentalAction | GAAction | DeprecatedAction,
    symbol_name: str,
    group_name: str,
) -> bool:
    if action.target == StabilityTarget.group:
        return action.name == group_name
    if action.target == StabilityTarget.symbol:
        return action.name == symbol_name and action.group == group_name
    return False


def get_symbol_since_version(
    symbol_name: str, changelog_actions: Sequence[ChangelogAction]
) -> str | None:
    for action in sorted(changelog_actions):
        if isinstance(action, MakePublicAction) and action.name == symbol_name:
            if version := find_release_version(action.ts, changelog_actions):
                return version
            return UNRELEASED_VERSION
    return None


def get_field_since_version(
    symbol_name: str,
    field_name: str,
    changelog_actions: Sequence[ChangelogAction],
) -> str | None:
    for action in sorted(changelog_actions):
        if (
            isinstance(action, AdditionalChangeAction)
            and action.name == symbol_name
            and action.field_name == field_name
        ):
            if version := find_release_version(action.ts, changelog_actions):
                return version
            return UNRELEASED_VERSION
    return get_symbol_since_version(symbol_name, changelog_actions)


def _action_description(action: ChangelogAction) -> str:
    match action:
        case MakePublicAction():
            return "Made public"
        case FixAction():
            return action.changelog_message or action.message
        case BreakingChangeAction():
            return action.details
        case AdditionalChangeAction():
            return action.details
        case RenameAction():
            return f"Renamed from `{action.old_name}`"
        case DeprecatedAction():
            if action.replacement:
                return f"Deprecated, use `{action.replacement}` instead"
            return "Deprecated"
    return ""


def build_symbol_changes(
    symbol_name: str, changelog_actions: Sequence[ChangelogAction]
) -> list[SymbolChange]:
    changes: list[SymbolChange] = []
    for action in sorted(changelog_actions):
        if isinstance(action, ReleaseAction):
            continue
        if action.name != symbol_name:
            continue
        version = (
            find_release_version(action.ts, changelog_actions) or UNRELEASED_VERSION
        )
        if isinstance(action, MakePublicAction):
            changes.append(
                SymbolChange(version=version, description="Made public", ts=action.ts)
            )
        elif isinstance(action, MEANINGFUL_CHANGE_ACTIONS):
            if desc := _action_description(action):
                changes.append(
                    SymbolChange(version=version, description=desc, ts=action.ts)
                )
    return sorted(
        changes, key=lambda c: (c.version != UNRELEASED_VERSION, c.ts), reverse=True
    )
