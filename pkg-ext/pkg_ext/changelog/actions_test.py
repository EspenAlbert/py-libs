from pathlib import Path

import pytest

from pkg_ext.changelog.actions import (
    BumpType,
    DeprecatedAction,
    ExperimentalAction,
    GAAction,
    StabilityTarget,
    archive_old_actions,
    changelog_filename,
    changelog_filepath,
)


def test_archive_old_actions_no_cleanup_when_below_trigger(tmp_path: Path):
    changelog_dir = tmp_path / "changelog"
    changelog_dir.mkdir()
    for i in range(1, 4):
        changelog_filepath(changelog_dir, i).write_text(f"content {i}")
    result = archive_old_actions(changelog_dir, cleanup_trigger=5, keep_count=2)
    assert result is False
    assert len(list(changelog_dir.glob("*.yaml"))) == 3


def test_archive_old_actions_cleanup_when_above_trigger(tmp_path: Path):
    changelog_dir = tmp_path / "changelog"
    changelog_dir.mkdir()
    file_contents = {}
    for i in range(1, 7):
        filename = changelog_filename(i)
        content = f"action: test_{i}\nts: 2023-01-{i:02d}T10:00:00Z"
        (changelog_dir / filename).write_text(content)
        file_contents[filename] = content
    result = archive_old_actions(changelog_dir, cleanup_trigger=5, keep_count=2)
    assert result is True
    remaining_files = list(changelog_dir.glob("*.yaml"))
    assert len(remaining_files) == 2
    archive_dir = changelog_dir / "000"
    assert archive_dir.exists()
    archived_in_000 = list(archive_dir.glob("*.yaml"))
    assert len(archived_in_000) == 4


@pytest.mark.parametrize(
    "action_class",
    [ExperimentalAction, GAAction, DeprecatedAction],
)
def test_stability_actions_return_patch_bump(action_class):
    action = action_class(
        name="some_function", target=StabilityTarget.symbol, author="test"
    )
    assert action.bump_type == BumpType.PATCH


def test_stability_arg_requires_parent():
    with pytest.raises(ValueError, match="parent required"):
        DeprecatedAction(name="arg_name", target=StabilityTarget.arg, author="test")


def test_stability_arg_parent_format():
    with pytest.raises(ValueError, match="group.*symbol_name"):
        DeprecatedAction(
            name="arg_name",
            target=StabilityTarget.arg,
            parent="missing_dot",
            author="test",
        )
    action = DeprecatedAction(
        name="format",
        target=StabilityTarget.arg,
        parent="my_group.some_function",
        author="test",
    )
    assert action.parent == "my_group.some_function"


def test_stability_action_yaml_roundtrip():
    yaml_content = """
name: my_group
type: experimental
target: group
ts: 2025-01-08T12:00:00Z
author: espen
"""
    from model_lib.serialize.yaml_serialize import parse_yaml_str

    from pkg_ext.changelog.actions import _changelog_action_adapter

    raw_data = parse_yaml_str(yaml_content)
    action = _changelog_action_adapter.validate_python(raw_data)
    assert action.name == "my_group"
    assert isinstance(action, ExperimentalAction)
    assert action.target == StabilityTarget.group
