from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from pkg_ext.changelog.actions import MakePublicAction, ReleaseAction
from pkg_ext.config import Stability
from pkg_ext.generation.docs_render import (
    calculate_source_link,
    format_docstring,
    format_signature,
    render_changes_section,
    render_env_var_table,
    render_example_section,
    render_field_table,
    render_inline_symbol,
    render_stability_badge,
    should_show_field_table,
)
from pkg_ext.generation.docs_version import SymbolChange
from pkg_ext.models.api_dump import (
    CallableSignature,
    ClassDump,
    ClassFieldInfo,
    ExceptionDump,
    FuncParamInfo,
    FunctionDump,
    GlobalVarDump,
    GroupDump,
    ParamDefault,
    ParamKind,
    TypeAliasDump,
)


def _func_dump(name: str) -> FunctionDump:
    return FunctionDump(name=name, module_path="mod", signature=CallableSignature())


def _class_dump(name: str, env_var: str | None = None) -> ClassDump:
    fields = None
    if env_var:
        fields = [ClassFieldInfo(name="field", env_vars=[env_var])]
    return ClassDump(name=name, module_path="mod", fields=fields)


def _class_with_fields(
    name: str, deprecated: str | None = None, description: str | None = None
) -> ClassDump:
    return ClassDump(
        name=name,
        module_path="mod",
        fields=[
            ClassFieldInfo(
                name="timeout",
                type_annotation="int",
                default=ParamDefault(value_repr="30"),
            ),
            ClassFieldInfo(
                name="strict",
                type_annotation="bool",
                default=ParamDefault(value_repr="False"),
                deprecated=deprecated,
                description=description,
            ),
        ],
    )


def test_format_signature_function():
    func = FunctionDump(
        name="parse",
        module_path="pkg.mod",
        signature=CallableSignature(
            parameters=[
                FuncParamInfo(
                    name="data",
                    kind=ParamKind.POSITIONAL_OR_KEYWORD,
                    type_annotation="str",
                ),
                FuncParamInfo(
                    name="strict",
                    kind=ParamKind.KEYWORD_ONLY,
                    type_annotation="bool",
                    default=ParamDefault(value_repr="False"),
                ),
            ],
            return_annotation="dict",
        ),
    )
    sig = format_signature(func)
    assert "def parse(data: str, *, strict: bool = False) -> dict:" in sig


def test_format_signature_class_with_fields():
    cls = ClassDump(
        name="MySettings",
        module_path="pkg.mod",
        direct_bases=["BaseSettings"],
        fields=[
            ClassFieldInfo(
                name="host",
                type_annotation="str",
                default=ParamDefault(value_repr="'localhost'"),
            ),
        ],
    )
    sig = format_signature(cls)
    assert "class MySettings(BaseSettings):" in sig
    assert "host: str = 'localhost'" in sig


def test_format_signature_exception():
    exc = ExceptionDump(
        name="MyError", module_path="pkg.mod", direct_bases=["ValueError"]
    )
    assert "class MyError(ValueError):" in format_signature(exc)


def test_format_signature_type_alias():
    alias = TypeAliasDump(
        name="Config", module_path="pkg.mod", alias_target="dict[str, Any]"
    )
    assert format_signature(alias) == "Config = dict[str, Any]"


def test_format_signature_global_var():
    var = GlobalVarDump(
        name="VERSION", module_path="pkg.mod", annotation="str", value_repr="'1.0.0'"
    )
    assert format_signature(var) == "VERSION: str = '1.0.0'"


def test_format_docstring():
    assert format_docstring("    Summary.\n\n    Details.") == "Summary.\n\nDetails."
    assert format_docstring("") == ""


def test_render_env_var_table():
    cls = ClassDump(
        name="Settings",
        module_path="pkg.mod",
        fields=[
            ClassFieldInfo(
                name="host",
                type_annotation="str",
                env_vars=["MY_HOST"],
                default=ParamDefault(value_repr="'localhost'"),
            ),
        ],
    )
    table = render_env_var_table(cls)
    assert "| `MY_HOST` | `host` |" in table


def test_should_show_field_table():
    cls = _class_with_fields("Config")
    assert not should_show_field_table(cls.fields)
    cls_dep = _class_with_fields("Config", deprecated="Use new")
    assert should_show_field_table(cls_dep.fields)
    assert should_show_field_table(cls.fields, {"timeout": "1.0.0"})


def test_render_field_table():
    cls = _class_with_fields("Config", deprecated="Use new")
    table = render_field_table(cls.fields)
    assert "| Field | Type | Default | Deprecated |" in table


def test_render_stability_badge():
    func = _func_dump("f")
    ga_group = GroupDump(name="g", stability=Stability.ga, symbols=[])
    exp_group = GroupDump(name="g", stability=Stability.experimental, symbols=[])
    assert render_stability_badge(func, ga_group) == ""
    assert "Experimental" in render_stability_badge(func, exp_group)


def test_calculate_source_link():
    doc_path = Path("/repo/docs/config/my_settings.md")
    link = calculate_source_link(doc_path, "config", Path("/repo"), "pkg_ext", 42)
    assert link == "../../pkg_ext/config.py#L42"


def test_render_changes_section():
    changes = [
        SymbolChange(
            version="1.0.0",
            description="Made public",
            ts=datetime(2025, 1, 1, tzinfo=UTC),
        ),
    ]
    content = render_changes_section(changes, "my_func")
    assert "| 1.0.0 | Made public |" in content


class ParseExample(BaseModel):
    example_name: str = "basic"
    example_description_md: str = "Parse a string"
    data: str = "hello"


def test_render_example_section():
    func = _func_dump("parse")
    example = ParseExample(example_name="basic", data="test")
    content = render_example_section(example, func, "my_pkg")
    assert "### Example: basic" in content
    assert "result = parse(data=" in content


# Import SymbolContext here to avoid circular import at module level
def test_render_inline_symbol():
    from pkg_ext.generation.docs import SymbolContext

    func = _func_dump("load")
    ctx = SymbolContext(symbol=func)
    content = render_inline_symbol(ctx)
    assert "### function: `load`" in content
    assert "def load(" in content


def test_render_inline_symbol_shows_since_badge():
    from pkg_ext.generation.docs import SymbolContext

    func = _func_dump("my_func")
    ctx = SymbolContext(symbol=func)
    actions = [
        MakePublicAction(
            name="my_func", group="config", ts=datetime(2025, 1, 1, tzinfo=UTC)
        ),
        ReleaseAction(
            name="1.0.0", old_version="0.0.0", ts=datetime(2025, 1, 10, tzinfo=UTC)
        ),
    ]
    content = render_inline_symbol(ctx, actions)
    assert "**Since:** 1.0.0" in content
