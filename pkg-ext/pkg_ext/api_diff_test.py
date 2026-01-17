from __future__ import annotations

from datetime import UTC, datetime

from pkg_ext.api_diff import (
    ChangeKind,
    DiffResult,
    compare_api_dumps,
    compare_fields,
    compare_params,
    normalize_type,
    types_equal,
)
from pkg_ext.changelog.actions import AdditionalChangeAction, BreakingChangeAction
from pkg_ext.models.api_dump import (
    ClassFieldInfo,
    FuncParamInfo,
    ParamDefault,
    ParamKind,
    PublicApiDump,
)


def _param(
    name: str,
    kind: ParamKind = ParamKind.POSITIONAL_OR_KEYWORD,
    type_annotation: str | None = None,
    default: ParamDefault | None = None,
) -> FuncParamInfo:
    return FuncParamInfo(
        name=name, kind=kind, type_annotation=type_annotation, default=default
    )


def _default(value: str, is_factory: bool = False) -> ParamDefault:
    return ParamDefault(value_repr=value, is_factory=is_factory)


def _field(
    name: str,
    type_annotation: str | None = None,
    default: ParamDefault | None = None,
    is_computed: bool = False,
) -> ClassFieldInfo:
    return ClassFieldInfo(
        name=name,
        type_annotation=type_annotation,
        default=default,
        is_computed=is_computed,
    )


def test_normalize_type_none_input():
    assert normalize_type(None) is None


def test_normalize_type_union_ordering():
    assert normalize_type("str | None") == "None | str"
    assert normalize_type("None | str") == "None | str"
    assert normalize_type("int | str | None") == "None | int | str"


def test_normalize_type_qualified_names():
    assert normalize_type("pathlib.Path") == "Path"
    assert normalize_type("list[pathlib.Path]") == "list[Path]"
    assert normalize_type("dict[str, pathlib.Path]") == "dict[str, Path]"


def test_types_equal():
    assert types_equal("str | None", "None | str")
    assert types_equal("pathlib.Path", "Path")
    assert not types_equal("str", "int")
    assert types_equal(None, None)


def test_compare_params_removed():
    baseline = [_param("x"), _param("y")]
    dev = [_param("x")]
    results = compare_params(baseline, dev, "func", "group")
    assert len(results) == 1
    assert results[0].change_kind == ChangeKind.PARAM_REMOVED
    assert "removed param 'y'" in results[0].details


def test_compare_params_required_added():
    baseline = [_param("x")]
    dev = [_param("x"), _param("y")]
    results = compare_params(baseline, dev, "func", "group")
    assert len(results) == 1
    assert results[0].change_kind == ChangeKind.REQUIRED_PARAM_ADDED


def test_compare_params_optional_added():
    baseline = [_param("x")]
    dev = [_param("x"), _param("y", default=_default("10"))]
    results = compare_params(baseline, dev, "func", "group")
    assert len(results) == 1
    assert results[0].change_kind == ChangeKind.OPTIONAL_PARAM_ADDED


def test_compare_params_type_changed():
    baseline = [_param("x", type_annotation="str")]
    dev = [_param("x", type_annotation="int")]
    results = compare_params(baseline, dev, "func", "group")
    assert len(results) == 1
    assert results[0].change_kind == ChangeKind.PARAM_TYPE_CHANGED
    assert "str -> int" in results[0].details


def test_compare_params_default_removed():
    baseline = [_param("x", default=_default("10"))]
    dev = [_param("x")]
    results = compare_params(baseline, dev, "func", "group")
    assert len(results) == 1
    assert results[0].change_kind == ChangeKind.DEFAULT_REMOVED


def test_compare_params_default_added():
    baseline = [_param("x")]
    dev = [_param("x", default=_default("10"))]
    results = compare_params(baseline, dev, "func", "group")
    assert len(results) == 1
    assert results[0].change_kind == ChangeKind.DEFAULT_ADDED


def test_compare_params_default_changed():
    baseline = [_param("x", default=_default("10"))]
    dev = [_param("x", default=_default("20"))]
    results = compare_params(baseline, dev, "func", "group")
    assert len(results) == 1
    assert results[0].change_kind == ChangeKind.DEFAULT_CHANGED
    assert "10 -> 20" in results[0].details


def test_compare_params_factory_defaults_no_false_positive():
    baseline = [_param("x", default=_default("...", is_factory=True))]
    dev = [_param("x", default=_default("...", is_factory=True))]
    results = compare_params(baseline, dev, "func", "group")
    assert len(results) == 0


def test_compare_params_skips_self():
    baseline = [_param("self"), _param("x")]
    dev = [_param("self")]
    results = compare_params(baseline, dev, "method", "group")
    assert len(results) == 1
    assert results[0].change_kind == ChangeKind.PARAM_REMOVED
    assert "removed param 'x'" in results[0].details


def test_compare_params_union_type_normalization():
    baseline = [_param("x", type_annotation="str | None")]
    dev = [_param("x", type_annotation="None | str")]
    results = compare_params(baseline, dev, "func", "group")
    assert len(results) == 0


def test_compare_fields_removed():
    baseline = [_field("x"), _field("y")]
    dev = [_field("x")]
    results = compare_fields(baseline, dev, "MyClass", "group")
    assert len(results) == 1
    assert results[0].change_kind == ChangeKind.FIELD_REMOVED


def test_compare_fields_required_added():
    baseline = [_field("x")]
    dev = [_field("x"), _field("y")]
    results = compare_fields(baseline, dev, "MyClass", "group")
    assert len(results) == 1
    assert results[0].change_kind == ChangeKind.REQUIRED_FIELD_ADDED


def test_compare_fields_optional_added():
    baseline = [_field("x")]
    dev = [_field("x"), _field("y", default=_default("None"))]
    results = compare_fields(baseline, dev, "MyClass", "group")
    assert len(results) == 1
    assert results[0].change_kind == ChangeKind.OPTIONAL_FIELD_ADDED


def test_compare_fields_skips_computed():
    baseline = [_field("x"), _field("computed", is_computed=True)]
    dev = [_field("x")]
    results = compare_fields(baseline, dev, "MyClass", "group")
    assert len(results) == 0


def test_diff_result_to_breaking_change_action():
    diff = DiffResult(
        name="func",
        group="core",
        action_type="breaking_change",
        change_kind=ChangeKind.PARAM_REMOVED,
        details="removed param 'x'",
    )
    action = diff.to_changelog_action()
    assert isinstance(action, BreakingChangeAction)
    assert action.name == "func"
    assert action.group == "core"
    assert action.auto_generated


def test_diff_result_to_additional_change_action():
    diff = DiffResult(
        name="func",
        group="core",
        action_type="additional_change",
        change_kind=ChangeKind.DEFAULT_ADDED,
        details="param 'x' default added: 10",
    )
    action = diff.to_changelog_action()
    assert isinstance(action, AdditionalChangeAction)
    assert action.auto_generated


def test_compare_api_dumps_none_baseline_returns_empty():
    dev = PublicApiDump(
        pkg_import_name="test",
        version="1.0.0",
        groups=[],
        dumped_at=datetime.now(UTC),
    )
    assert compare_api_dumps(None, dev) == []
