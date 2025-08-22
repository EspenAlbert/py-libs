from typing import Callable

import pytest
from model_lib.serialize.parse import parse_model

from pkg_ext.models import PublicGroup, PublicGroups, RefSymbol, SymbolType
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


def test_public_groups_dumping(_public_groups, _public_group_check):
    _public_groups.add_group(PublicGroup(name="test"))
    groups_after = _public_group_check()
    assert groups_after.groups == [
        PublicGroup(name="__ROOT__"),
        PublicGroup(name="test"),
    ]


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
    group = PublicGroup(name="test")
    added_group = _public_groups.add_group(group)
    assert added_group == group
    _public_groups.add_ref(ref, "test")
    assert _public_groups.groups_no_root == [
        PublicGroup(name="test", owned_refs={"my_module.my_func"})
    ]
