"""Tests for stability target parsing and validation."""

import pytest

from pkg_ext.cli.stability import ParsedTarget, StabilityLevel


def test_parse_group_target():
    target = ParsedTarget.parse("config")
    assert target.level == StabilityLevel.group
    assert target.group == "config"
    assert target.symbol is None
    assert target.arg is None


def test_parse_symbol_target():
    target = ParsedTarget.parse("config.parse")
    assert target.level == StabilityLevel.symbol
    assert target.group == "config"
    assert target.symbol == "parse"
    assert target.arg is None


def test_parse_arg_target():
    target = ParsedTarget.parse("config.parse.timeout")
    assert target.level == StabilityLevel.arg
    assert target.group == "config"
    assert target.symbol == "parse"
    assert target.arg == "timeout"
    assert target.parent == "config.parse"


def test_parse_invalid_target():
    with pytest.raises(ValueError, match="Invalid target format"):
        ParsedTarget.parse("a.b.c.d")


def test_stability_state_tracking():
    from pathlib import Path

    from pkg_ext.changelog.actions import (
        DeprecatedAction,
        ExperimentalAction,
        GAAction,
        StabilityTarget,
    )
    from pkg_ext.config import Stability
    from pkg_ext.models.groups import PublicGroups
    from pkg_ext.pkg_state import PkgExtState

    state = PkgExtState(
        repo_root=Path(),
        changelog_dir=Path(),
        pkg_path=Path("code/py-libs/pkg-ext/pkg_ext"),
        groups=PublicGroups(),
    )

    # Default is GA
    assert state.get_group_stability("any_group") == Stability.ga

    # Test group stability tracking
    exp_action = ExperimentalAction(name="mygroup", target=StabilityTarget.group)
    state.update_state(exp_action)
    assert state.get_group_stability("mygroup") == Stability.experimental

    ga_action = GAAction(name="mygroup", target=StabilityTarget.group)
    state.update_state(ga_action)
    assert state.get_group_stability("mygroup") == Stability.ga

    # Test symbol inherits from group
    assert state.get_symbol_stability("mygroup", "sym") == Stability.ga

    # Test symbol override
    sym_exp = ExperimentalAction(
        name="sym", target=StabilityTarget.symbol, group="mygroup"
    )
    state.update_state(sym_exp)
    assert state.get_symbol_stability("mygroup", "sym") == Stability.experimental

    # Test arg inherits from symbol
    assert state.get_arg_stability("mygroup", "sym", "arg1") == Stability.experimental

    # Test arg override
    arg_dep = DeprecatedAction(
        name="arg1",
        target=StabilityTarget.arg,
        parent="mygroup.sym",
        replacement="new_arg",
    )
    state.update_state(arg_dep)
    assert state.get_arg_stability("mygroup", "sym", "arg1") == Stability.deprecated
