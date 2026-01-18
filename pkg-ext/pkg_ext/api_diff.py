from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

from model_lib import Event
from zero_3rdparty.enum_utils import StrEnum

from pkg_ext.changelog.actions import AdditionalChangeAction, BreakingChangeAction
from pkg_ext.models.api_dump import (
    ClassDump,
    ClassFieldInfo,
    ExceptionDump,
    FuncParamInfo,
    FunctionDump,
    GlobalVarDump,
    GroupDump,
    ParamDefault,
    ParamKind,
    PublicApiDump,
    SymbolDump,
    TypeAliasDump,
)


class ChangeKind(StrEnum):
    # Breaking changes
    REQUIRED_PARAM_ADDED = "required_param_added"
    PARAM_REMOVED = "param_removed"
    PARAM_TYPE_CHANGED = "param_type_changed"
    RETURN_TYPE_CHANGED = "return_type_changed"
    REQUIRED_FIELD_ADDED = "required_field_added"
    FIELD_REMOVED = "field_removed"
    BASE_CLASS_REMOVED = "base_class_removed"
    DEFAULT_REMOVED = "default_removed"
    # Non-breaking changes
    OPTIONAL_PARAM_ADDED = "optional_param_added"
    DEFAULT_CHANGED = "default_changed"
    DEFAULT_ADDED = "default_added"
    OPTIONAL_FIELD_ADDED = "optional_field_added"

    @property
    def is_breaking(self) -> bool:
        return self in _BREAKING_KINDS


_BREAKING_KINDS = frozenset(
    {
        ChangeKind.REQUIRED_PARAM_ADDED,
        ChangeKind.PARAM_REMOVED,
        ChangeKind.PARAM_TYPE_CHANGED,
        ChangeKind.RETURN_TYPE_CHANGED,
        ChangeKind.REQUIRED_FIELD_ADDED,
        ChangeKind.FIELD_REMOVED,
        ChangeKind.BASE_CLASS_REMOVED,
        ChangeKind.DEFAULT_REMOVED,
    }
)


class DiffResult(Event):
    name: str
    group: str
    action_type: Literal["breaking_change", "additional_change"]
    change_kind: ChangeKind
    details: str
    field_name: str | None = None

    def to_changelog_action(self) -> BreakingChangeAction | AdditionalChangeAction:
        if self.action_type == "breaking_change":
            return BreakingChangeAction(
                name=self.name,
                group=self.group,
                details=self.details,
                change_kind=self.change_kind,
                field_name=self.field_name,
                auto_generated=True,
            )
        return AdditionalChangeAction(
            name=self.name,
            group=self.group,
            details=self.details,
            change_kind=self.change_kind,
            field_name=self.field_name,
            auto_generated=True,
        )


_QUALIFIED_NAME_RE = re.compile(r"(?<![.\w])(\w+\.)+(\w+)")


def normalize_type(t: str | None) -> str | None:
    if t is None:
        return None
    normalized = _QUALIFIED_NAME_RE.sub(r"\2", t)
    if " | " in normalized:
        parts = [p.strip() for p in normalized.split(" | ")]
        normalized = " | ".join(sorted(parts))
    return normalized


def types_equal(baseline: str | None, dev: str | None) -> bool:
    return normalize_type(baseline) == normalize_type(dev)


def _is_required(param: FuncParamInfo) -> bool:
    return param.default is None and param.kind not in (
        ParamKind.VAR_POSITIONAL,
        ParamKind.VAR_KEYWORD,
    )


def _is_field_required(field: ClassFieldInfo) -> bool:
    return field.default is None and not field.is_computed


def _compare_defaults(
    base_default: ParamDefault | None,
    dev_default: ParamDefault | None,
    symbol_name: str,
    group: str,
    item_name: str,
    item_type: Literal["param", "field"],
    is_field: bool = False,
) -> DiffResult | None:
    field_name = item_name if is_field else None
    if base_default is None and dev_default is not None:
        return _diff(
            symbol_name,
            group,
            ChangeKind.DEFAULT_ADDED,
            f"{item_type} '{item_name}' default added: {dev_default.value_repr}",
            field_name=field_name,
        )
    if base_default is not None and dev_default is None:
        return _diff(
            symbol_name,
            group,
            ChangeKind.DEFAULT_REMOVED,
            f"{item_type} '{item_name}' default removed (was: {base_default.value_repr})",
            field_name=field_name,
        )
    if base_default and dev_default:
        if base_default.is_factory and dev_default.is_factory:
            if base_default.value_repr == dev_default.value_repr == "...":
                return None
        if base_default.value_repr != dev_default.value_repr:
            return _diff(
                symbol_name,
                group,
                ChangeKind.DEFAULT_CHANGED,
                f"{item_type} '{item_name}' default: {base_default.value_repr} -> {dev_default.value_repr}",
                field_name=field_name,
            )
    return None


def _diff(
    name: str,
    group: str,
    change_kind: ChangeKind,
    details: str,
    field_name: str | None = None,
) -> DiffResult:
    return DiffResult(
        name=name,
        group=group,
        action_type="breaking_change"
        if change_kind.is_breaking
        else "additional_change",
        change_kind=change_kind,
        details=details,
        field_name=field_name,
    )


def compare_params(
    baseline: list[FuncParamInfo],
    dev: list[FuncParamInfo],
    symbol_name: str,
    group: str,
) -> list[DiffResult]:
    results: list[DiffResult] = []
    base_map = {p.name: p for p in baseline if p.name != "self"}
    dev_map = {p.name: p for p in dev if p.name != "self"}

    for name in base_map.keys() - dev_map.keys():
        results.append(
            _diff(
                symbol_name,
                group,
                ChangeKind.PARAM_REMOVED,
                f"removed param '{name}'",
            )
        )

    for name in dev_map.keys() - base_map.keys():
        p = dev_map[name]
        if _is_required(p):
            results.append(
                _diff(
                    symbol_name,
                    group,
                    ChangeKind.REQUIRED_PARAM_ADDED,
                    f"added required param '{name}'",
                )
            )
        else:
            default_str = p.default.value_repr if p.default else "None"
            results.append(
                _diff(
                    symbol_name,
                    group,
                    ChangeKind.OPTIONAL_PARAM_ADDED,
                    f"added optional param '{name}' (default: {default_str})",
                )
            )

    for name in base_map.keys() & dev_map.keys():
        bp, dp = base_map[name], dev_map[name]
        if not types_equal(bp.type_annotation, dp.type_annotation):
            results.append(
                _diff(
                    symbol_name,
                    group,
                    ChangeKind.PARAM_TYPE_CHANGED,
                    f"param '{name}' type: {bp.type_annotation} -> {dp.type_annotation}",
                )
            )
        if default_diff := _compare_defaults(
            bp.default, dp.default, symbol_name, group, name, "param"
        ):
            results.append(default_diff)

    return results


def compare_fields(
    baseline: list[ClassFieldInfo],
    dev: list[ClassFieldInfo],
    symbol_name: str,
    group: str,
) -> list[DiffResult]:
    results: list[DiffResult] = []
    base_map = {f.name: f for f in baseline if not f.is_computed}
    dev_map = {f.name: f for f in dev if not f.is_computed}

    for name in base_map.keys() - dev_map.keys():
        results.append(
            _diff(
                symbol_name,
                group,
                ChangeKind.FIELD_REMOVED,
                f"removed field '{name}'",
                field_name=name,
            )
        )

    for name in dev_map.keys() - base_map.keys():
        f = dev_map[name]
        if _is_field_required(f):
            results.append(
                _diff(
                    symbol_name,
                    group,
                    ChangeKind.REQUIRED_FIELD_ADDED,
                    f"added required field '{name}'",
                    field_name=name,
                )
            )
        else:
            default_str = f.default.value_repr if f.default else "None"
            results.append(
                _diff(
                    symbol_name,
                    group,
                    ChangeKind.OPTIONAL_FIELD_ADDED,
                    f"added optional field '{name}' (default: {default_str})",
                    field_name=name,
                )
            )

    for name in base_map.keys() & dev_map.keys():
        bf, df = base_map[name], dev_map[name]
        if not types_equal(bf.type_annotation, df.type_annotation):
            results.append(
                _diff(
                    symbol_name,
                    group,
                    ChangeKind.PARAM_TYPE_CHANGED,
                    f"field '{name}' type: {bf.type_annotation} -> {df.type_annotation}",
                    field_name=name,
                )
            )
        if default_diff := _compare_defaults(
            bf.default, df.default, symbol_name, group, name, "field", is_field=True
        ):
            results.append(default_diff)

    return results


def compare_function(
    baseline: FunctionDump, dev: FunctionDump, group: str
) -> list[DiffResult]:
    results = compare_params(
        baseline.signature.parameters,
        dev.signature.parameters,
        baseline.name,
        group,
    )
    if not types_equal(
        baseline.signature.return_annotation, dev.signature.return_annotation
    ):
        results.append(
            _diff(
                baseline.name,
                group,
                ChangeKind.RETURN_TYPE_CHANGED,
                f"return type: {baseline.signature.return_annotation} -> {dev.signature.return_annotation}",
            )
        )
    return results


def _compare_bases(
    baseline: list[str], dev: list[str], symbol_name: str, group: str
) -> list[DiffResult]:
    return [
        _diff(
            symbol_name,
            group,
            ChangeKind.BASE_CLASS_REMOVED,
            f"removed base class '{base}'",
        )
        for base in set(baseline) - set(dev)
    ]


def compare_class(baseline: ClassDump, dev: ClassDump, group: str) -> list[DiffResult]:
    results = _compare_bases(
        baseline.direct_bases, dev.direct_bases, baseline.name, group
    )
    if baseline.fields and dev.fields:
        results.extend(
            compare_fields(baseline.fields, dev.fields, baseline.name, group)
        )
    return results


def compare_exception(
    baseline: ExceptionDump, dev: ExceptionDump, group: str
) -> list[DiffResult]:
    results = _compare_bases(
        baseline.direct_bases, dev.direct_bases, baseline.name, group
    )
    if baseline.init_signature and dev.init_signature:
        results.extend(
            compare_params(
                baseline.init_signature.parameters,
                dev.init_signature.parameters,
                baseline.name,
                group,
            )
        )
    return results


def compare_global_var(
    baseline: GlobalVarDump, dev: GlobalVarDump, group: str
) -> list[DiffResult]:
    if not types_equal(baseline.annotation, dev.annotation):
        return [
            _diff(
                baseline.name,
                group,
                ChangeKind.PARAM_TYPE_CHANGED,
                f"type: {baseline.annotation} -> {dev.annotation}",
            )
        ]
    return []


def compare_symbols(
    baseline: SymbolDump, dev: SymbolDump, group: str
) -> list[DiffResult]:
    if baseline.type != dev.type:
        return []  # Type changed handled as remove+add at higher level
    match baseline:
        case FunctionDump():
            assert isinstance(dev, FunctionDump)
            return compare_function(baseline, dev, group)
        case ClassDump():
            assert isinstance(dev, ClassDump)
            return compare_class(baseline, dev, group)
        case ExceptionDump():
            assert isinstance(dev, ExceptionDump)
            return compare_exception(baseline, dev, group)
        case GlobalVarDump():
            assert isinstance(dev, GlobalVarDump)
            return compare_global_var(baseline, dev, group)
        case TypeAliasDump():
            return []  # Type alias changes not tracked
    return []


def compare_group(baseline: GroupDump, dev: GroupDump) -> list[DiffResult]:
    results: list[DiffResult] = []
    base_map = {s.name: s for s in baseline.symbols}
    dev_map = {s.name: s for s in dev.symbols}
    # Only compare modified symbols - additions/removals handled by pre-change actions
    for name in base_map.keys() & dev_map.keys():
        results.extend(compare_symbols(base_map[name], dev_map[name], baseline.name))
    return results


def compare_api_dumps(
    baseline: PublicApiDump | None, dev: PublicApiDump
) -> list[DiffResult]:
    if baseline is None:
        return []  # First release, no comparison
    results: list[DiffResult] = []
    base_groups = {g.name: g for g in baseline.groups}
    dev_groups = {g.name: g for g in dev.groups}
    for name in base_groups.keys() & dev_groups.keys():
        results.extend(compare_group(base_groups[name], dev_groups[name]))
    return results


def format_diff_results(results: list[DiffResult]) -> str:
    """Format diff results grouped by breaking/non-breaking."""
    if not results:
        return "No API changes detected."

    breaking = [r for r in results if r.action_type == "breaking_change"]
    additional = [r for r in results if r.action_type == "additional_change"]
    lines: list[str] = []

    if breaking:
        lines.append(f"=== Breaking Changes ({len(breaking)}) ===")
        for r in breaking:
            lines.append(f"[{r.group}] {r.name}: {r.details}")
        lines.append("")

    if additional:
        lines.append(f"=== Additional Changes ({len(additional)}) ===")
        for r in additional:
            lines.append(f"[{r.group}] {r.name}: {r.details}")
        lines.append("")

    lines.append(
        f"Summary: {len(breaking)} breaking, {len(additional)} additional changes"
    )
    return "\n".join(lines)


def _action_key(
    action: BreakingChangeAction | AdditionalChangeAction,
) -> tuple[str, str, str, str]:
    return (action.name, action.group, action.type, action.change_kind or "")


def reconcile_auto_actions(
    existing: Sequence[BreakingChangeAction | AdditionalChangeAction],
    new_diff: Sequence[DiffResult],
) -> list[BreakingChangeAction | AdditionalChangeAction]:
    existing_by_key = {_action_key(a): a for a in existing if a.auto_generated}
    result: list[BreakingChangeAction | AdditionalChangeAction] = []
    for diff in new_diff:
        new_action = diff.to_changelog_action()
        key = _action_key(new_action)
        if old := existing_by_key.get(key):
            result.append(old.model_copy(update={"details": diff.details}))
        else:
            result.append(new_action)
    return result
