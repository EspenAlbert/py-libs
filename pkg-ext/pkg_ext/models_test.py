from datetime import datetime, timezone
from typing import Callable

import pytest
from model_lib.serialize.parse import parse_model

from pkg_ext.changelog.actions import (
    ChangelogAction,
    ChangelogActionType,
    GroupModulePathChangelog,
    changelog_filepath,
    dump_changelog_actions,
)
from pkg_ext.changelog.parser import parse_changelog
from pkg_ext.models import (
    PublicGroups,
    RefSymbol,
    SymbolType,
)
from pkg_ext.settings import PkgSettings


@pytest.fixture()
def _public_groups(tmp_path) -> PublicGroups:
    path = tmp_path / PkgSettings.PUBLIC_GROUPS_STORAGE_FILENAME
    return PublicGroups(storage_path=path)


@pytest.fixture()
def _public_group_check(
    _public_groups, file_regression_testdata
) -> Callable[[], PublicGroups]:
    def check():
        file_regression_testdata(_public_groups.storage_path.read_text(), "yaml")
        return parse_model(_public_groups.storage_path, t=PublicGroups)

    return check


def test_public_groups_dumping_after_new_ref_symbol(
    _public_groups, _public_group_check
):
    ref = RefSymbol(name="my_func", type=SymbolType.FUNCTION, rel_path="my_module")
    _public_groups.add_ref(ref, "test")
    groups = _public_group_check()
    test_group = groups.matching_group(ref)
    assert test_group.name == "test"
    assert test_group.owned_refs == {"my_module.my_func"}


def test_public_groups_add_to_existing_group(_public_groups, _public_group_check):
    ref = RefSymbol(name="my_func", type=SymbolType.FUNCTION, rel_path="my_module")
    ref2 = RefSymbol(name="my_func2", type=SymbolType.FUNCTION, rel_path="my_module")
    _public_groups.add_ref(ref, "test")
    _public_groups.add_ref(ref2, "test")
    assert len(_public_groups.groups_no_root) == 1
    _public_group_check()


def test_tool_state_update_state(settings):
    actions = [
        ChangelogAction(
            name="git_inferred",
            type=ChangelogActionType.GROUP_MODULE,
            ts=datetime(2025, 8, 25, 17, 37, 2, tzinfo=timezone.utc),
            author="UNSET",
            details=GroupModulePathChangelog(
                module_path="inferred", type="group_module_path"
            ),
        ),
        ChangelogAction(
            name="inferred",
            type=ChangelogActionType.EXPOSE,
            ts=datetime(2025, 8, 25, 17, 37, 2, tzinfo=timezone.utc),
            author="UNSET",
            details="created in inferred.py",
        ),
    ]
    dump_changelog_actions(changelog_filepath(settings.changelog_dir, 1), actions)
    state, _ = parse_changelog(settings)
    assert [group.name for group in state.groups.groups_no_root] == ["git_inferred"]
