"""Target parsing and validation for stability CLI commands."""

from __future__ import annotations

import inspect
from pydoc import locate
from typing import Self

from model_lib import Entity
from zero_3rdparty.enum_utils import StrEnum

from pkg_ext.changelog.actions import StabilityTarget
from pkg_ext.config import Stability
from pkg_ext.models.code_state import PkgCodeState
from pkg_ext.models.groups import PublicGroups
from pkg_ext.pkg_state import PkgExtState


class StabilityLevel(StrEnum):
    group = "group"
    symbol = "symbol"
    arg = "arg"


class ParsedTarget(Entity):
    level: StabilityLevel
    group: str
    symbol: str | None = None
    arg: str | None = None

    @classmethod
    def parse(cls, target: str) -> Self:
        parts = target.split(".")
        match len(parts):
            case 1:
                return cls(level=StabilityLevel.group, group=parts[0])
            case 2:
                return cls(level=StabilityLevel.symbol, group=parts[0], symbol=parts[1])
            case 3:
                return cls(
                    level=StabilityLevel.arg,
                    group=parts[0],
                    symbol=parts[1],
                    arg=parts[2],
                )
            case _:
                raise ValueError(
                    f"Invalid target format: {target}. Expected group, group.symbol, or group.symbol.arg"
                )

    def as_stability_target(self) -> StabilityTarget:
        return StabilityTarget(self.level.value)

    @property
    def symbol_name(self) -> str:
        assert self.symbol, f"symbol_name called on group-level target: {self}"
        return self.symbol

    @property
    def arg_name(self) -> str:
        assert self.arg, f"arg_name called on non-arg-level target: {self}"
        return self.arg

    @property
    def parent(self) -> str:
        assert self.level == StabilityLevel.arg, (
            f"parent called on non-arg target: {self}"
        )
        return f"{self.group}.{self.symbol}"


def validate_group_exists(target: ParsedTarget, groups: PublicGroups) -> None:
    if target.group not in groups.name_to_group:
        available = sorted(groups.name_to_group.keys())
        raise ValueError(
            f"Group '{target.group}' not found. Available: {', '.join(available)}"
        )


def validate_symbol_exists(
    target: ParsedTarget, code_state: PkgCodeState, groups: PublicGroups
) -> None:
    if not target.symbol:
        return
    validate_group_exists(target, groups)
    group = groups.name_to_group[target.group]
    # Check if symbol is in the group's owned modules
    for ref in code_state.import_id_refs.values():
        if ref.name == target.symbol and ref.module_path in group.owned_modules:
            return
    raise ValueError(f"Symbol '{target.symbol}' not found in group '{target.group}'")


def validate_arg_exists(
    target: ParsedTarget, code_state: PkgCodeState, groups: PublicGroups
) -> None:
    if not target.arg or not target.symbol:
        return
    validate_symbol_exists(target, code_state, groups)
    # Locate the function and check signature
    group = groups.name_to_group[target.group]
    for ref in code_state.import_id_refs.values():
        if ref.name == target.symbol and ref.module_path in group.owned_modules:
            full_id = ref.full_id(code_state.pkg_import_name)
            obj = locate(full_id)
            if obj is None:
                raise ValueError(f"Cannot locate '{full_id}'")
            if not callable(obj):
                raise ValueError(f"'{target.symbol}' is not callable, cannot have args")
            sig = inspect.signature(obj)
            if target.arg not in sig.parameters:
                available = list(sig.parameters.keys())
                raise ValueError(
                    f"Arg '{target.arg}' not found on '{target.symbol}'. Available: {available}"
                )
            return
    raise ValueError(f"Symbol '{target.symbol}' not found in group '{target.group}'")


def validate_target(
    target: ParsedTarget, code_state: PkgCodeState, groups: PublicGroups
) -> None:
    match target.level:
        case StabilityLevel.group:
            validate_group_exists(target, groups)
        case StabilityLevel.symbol:
            validate_symbol_exists(target, code_state, groups)
        case StabilityLevel.arg:
            validate_arg_exists(target, code_state, groups)


def validate_group_is_ga(target: ParsedTarget, tool_state: PkgExtState) -> None:
    """For arg-level stability changes, the group must be GA."""
    if target.level != StabilityLevel.arg:
        return
    group_stability = tool_state.get_group_stability(target.group)
    if group_stability != Stability.ga:
        raise ValueError(
            f"Cannot set arg-level stability when group '{target.group}' is {group_stability}. "
            "Graduate the group to GA first with: pkg-ext ga {group}"
        )
