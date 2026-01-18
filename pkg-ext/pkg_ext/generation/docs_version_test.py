from datetime import UTC, datetime

from pkg_ext.changelog.actions import (
    AdditionalChangeAction,
    DeprecatedAction,
    FixAction,
    MakePublicAction,
    ReleaseAction,
    RenameAction,
    StabilityTarget,
)
from pkg_ext.generation.docs_version import (
    UNRELEASED_VERSION,
    build_symbol_changes,
    find_release_version,
    get_field_since_version,
    get_symbol_since_version,
)


def test_find_release_version_found():
    actions = [
        ReleaseAction(
            name="1.0.0", old_version="0.0.0", ts=datetime(2025, 1, 10, tzinfo=UTC)
        ),
    ]
    assert find_release_version(datetime(2025, 1, 5, tzinfo=UTC), actions) == "1.0.0"


def test_find_release_version_not_found():
    actions = [
        ReleaseAction(
            name="1.0.0", old_version="0.0.0", ts=datetime(2025, 1, 1, tzinfo=UTC)
        ),
    ]
    assert find_release_version(datetime(2025, 2, 1, tzinfo=UTC), actions) is None


def test_get_symbol_since_version_with_release():
    actions = [
        MakePublicAction(
            name="my_func", group="config", ts=datetime(2025, 1, 1, tzinfo=UTC)
        ),
        ReleaseAction(
            name="1.0.0", old_version="0.0.0", ts=datetime(2025, 1, 10, tzinfo=UTC)
        ),
    ]
    assert get_symbol_since_version("my_func", actions) == "1.0.0"


def test_get_symbol_since_version_unreleased():
    actions = [
        MakePublicAction(
            name="my_func", group="config", ts=datetime(2025, 1, 1, tzinfo=UTC)
        ),
    ]
    assert get_symbol_since_version("my_func", actions) == UNRELEASED_VERSION


def test_get_field_since_version_from_action():
    actions = [
        AdditionalChangeAction(
            name="MyClass",
            group="config",
            details="added field",
            field_name="new_field",
            ts=datetime(2025, 1, 1, tzinfo=UTC),
        ),
        ReleaseAction(
            name="1.1.0", old_version="1.0.0", ts=datetime(2025, 1, 10, tzinfo=UTC)
        ),
    ]
    assert get_field_since_version("MyClass", "new_field", actions) == "1.1.0"


def test_get_field_since_version_falls_back_to_symbol():
    actions = [
        MakePublicAction(
            name="MyClass", group="config", ts=datetime(2025, 1, 1, tzinfo=UTC)
        ),
        ReleaseAction(
            name="1.0.0", old_version="0.0.0", ts=datetime(2025, 1, 10, tzinfo=UTC)
        ),
    ]
    assert get_field_since_version("MyClass", "existing_field", actions) == "1.0.0"


def test_build_symbol_changes_unreleased():
    actions = [
        MakePublicAction(
            name="my_func", group="config", ts=datetime(2025, 1, 1, tzinfo=UTC)
        ),
        FixAction(
            name="my_func",
            short_sha="abc",
            message="fix bug",
            ts=datetime(2025, 1, 2, tzinfo=UTC),
        ),
    ]
    changes = build_symbol_changes("my_func", actions)
    assert len(changes) == 2
    assert all(c.version == UNRELEASED_VERSION for c in changes)


def test_build_symbol_changes_with_releases():
    actions = [
        MakePublicAction(
            name="parse", group="config", ts=datetime(2025, 1, 1, tzinfo=UTC)
        ),
        ReleaseAction(
            name="1.0.0", old_version="0.0.0", ts=datetime(2025, 1, 5, tzinfo=UTC)
        ),
        FixAction(
            name="parse",
            short_sha="def",
            message="fix parse",
            ts=datetime(2025, 1, 10, tzinfo=UTC),
        ),
    ]
    changes = build_symbol_changes("parse", actions)
    assert len(changes) == 2
    versions = [c.version for c in changes]
    assert "1.0.0" in versions
    assert UNRELEASED_VERSION in versions


def test_build_symbol_changes_deprecated_action():
    actions = [
        DeprecatedAction(
            name="old_func",
            target=StabilityTarget.symbol,
            group="config",
            replacement="new_func",
            ts=datetime(2025, 1, 1, tzinfo=UTC),
        ),
    ]
    changes = build_symbol_changes("old_func", actions)
    assert len(changes) == 1
    assert "new_func" in changes[0].description


def test_build_symbol_changes_rename_action():
    actions = [
        RenameAction(
            name="new_name",
            group="config",
            old_name="old_name",
            ts=datetime(2025, 1, 1, tzinfo=UTC),
        ),
    ]
    changes = build_symbol_changes("new_name", actions)
    assert len(changes) == 1
    assert "old_name" in changes[0].description
