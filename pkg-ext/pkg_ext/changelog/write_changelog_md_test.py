from unittest.mock import MagicMock

import pytest

from pkg_ext.changelog.actions import (
    AdditionalChangeAction,
    BreakingChangeAction,
    ChoreAction,
    DeleteAction,
    DeprecatedAction,
    ExperimentalAction,
    FixAction,
    GAAction,
    MakePublicAction,
    RenameAction,
    StabilityTarget,
)
from pkg_ext.changelog.write_changelog_md import as_changelog_line


@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.code_state.ref_symbol.return_value = MagicMock(type="function")
    return ctx


def test_fix_action_ignored_returns_empty(mock_ctx):
    action = FixAction(
        name="grp", short_sha="abc123", message="fix bug", ignored=True, author="test"
    )
    assert as_changelog_line(action, "https://github.com/user/repo", mock_ctx) == ""


def test_fix_action_uses_changelog_message_when_set(mock_ctx):
    action = FixAction(
        name="grp",
        short_sha="abc123",
        message="fix: internal message",
        changelog_message="Fixed the bug",
        author="test",
    )
    result = as_changelog_line(action, "https://github.com/user/repo", mock_ctx)
    assert result.startswith("Fixed the bug")
    assert "abc123" in result


def test_make_public_action(mock_ctx):
    action = MakePublicAction(name="my_func", group="utils", author="test")
    result = as_changelog_line(action, "", mock_ctx)
    assert result == "New function `my_func`"


def test_delete_action(mock_ctx):
    action = DeleteAction(name="old_func", group="utils", author="test")
    assert as_changelog_line(action, "", mock_ctx) == "Removed `utils.old_func`"


def test_rename_action(mock_ctx):
    action = RenameAction(
        name="new_name", old_name="old_name", group="api", author="test"
    )
    assert (
        as_changelog_line(action, "", mock_ctx)
        == "Renamed `api.old_name` to `new_name`"
    )


def test_breaking_change_action(mock_ctx):
    action = BreakingChangeAction(
        name="parse", group="config", details="removed strict param", author="test"
    )
    result = as_changelog_line(action, "", mock_ctx)
    assert result == "BREAKING `config.parse`: removed strict param"


def test_additional_change_action(mock_ctx):
    action = AdditionalChangeAction(
        name="Config", group="settings", details="added timeout field", author="test"
    )
    assert (
        as_changelog_line(action, "", mock_ctx)
        == "`settings.Config`: added timeout field"
    )


@pytest.mark.parametrize(
    ("action_cls", "prefix"),
    [(ExperimentalAction, "Experimental"), (GAAction, "GA")],
)
def test_stability_actions_group_target(mock_ctx, action_cls, prefix):
    action = action_cls(name="my_group", target=StabilityTarget.group, author="test")
    assert as_changelog_line(action, "", mock_ctx) == f"{prefix}: group `my_group`"


@pytest.mark.parametrize(
    ("action_cls", "prefix"),
    [(ExperimentalAction, "Experimental"), (GAAction, "GA")],
)
def test_stability_actions_symbol_target(mock_ctx, action_cls, prefix):
    action = action_cls(
        name="func", target=StabilityTarget.symbol, group="utils", author="test"
    )
    assert as_changelog_line(action, "", mock_ctx) == f"{prefix}: `utils.func`"


def test_deprecated_with_replacement(mock_ctx):
    action = DeprecatedAction(
        name="old_api",
        target=StabilityTarget.group,
        replacement="new_api",
        author="test",
    )
    result = as_changelog_line(action, "", mock_ctx)
    assert result == "Deprecated: group `old_api`, use `new_api` instead"


def test_deprecated_without_replacement(mock_ctx):
    action = DeprecatedAction(
        name="legacy", target=StabilityTarget.group, author="test"
    )
    assert as_changelog_line(action, "", mock_ctx) == "Deprecated: group `legacy`"


def test_chore_action(mock_ctx):
    action = ChoreAction(description="updated dependencies", author="test")
    assert as_changelog_line(action, "", mock_ctx) == "Chore: updated dependencies"
