from datetime import UTC, datetime
from pathlib import Path

from zero_3rdparty.sections import parse_sections

from pkg_ext.changelog.actions import FixAction, MakePublicAction
from pkg_ext.config import (
    PKG_EXT_TOOL_NAME,
    ROOT_GROUP_NAME,
    GroupConfig,
    ProjectConfig,
    Stability,
)
from pkg_ext.generation.docs import (
    MD_CONFIG,
    ROOT_DIR,
    GeneratedDocsOutput,
    SymbolContext,
    build_symbol_context,
    calculate_source_link,
    format_docstring,
    format_signature,
    generate_docs,
    group_dir_name,
    has_env_vars,
    render_env_var_table,
    render_group_index,
    render_stability_badge,
)
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
    PublicApiDump,
    TypeAliasDump,
)


def _func_dump(name: str) -> FunctionDump:
    return FunctionDump(name=name, module_path="mod", signature=CallableSignature())


def _class_dump(name: str, env_var: str | None = None) -> ClassDump:
    fields = None
    if env_var:
        fields = [ClassFieldInfo(name="field", env_vars=[env_var])]
    return ClassDump(name=name, module_path="mod", fields=fields)


def test_group_dir_name_root():
    group = GroupDump(name=ROOT_GROUP_NAME, symbols=[])
    assert group_dir_name(group) == ROOT_DIR


def test_group_dir_name_regular():
    group = GroupDump(name="config", symbols=[])
    assert group_dir_name(group) == "config"


def test_has_env_vars():
    func = _func_dump("func")
    assert not has_env_vars(func)
    cls_no_env = _class_dump("NoEnv")
    assert not has_env_vars(cls_no_env)
    cls_with_env = _class_dump("WithEnv", env_var="MY_VAR")
    assert has_env_vars(cls_with_env)


def test_symbol_context_complexity():
    simple = SymbolContext(symbol=_func_dump("simple"))
    assert not simple.is_complex

    with_examples = SymbolContext(symbol=_func_dump("ex"), has_examples=True)
    assert with_examples.is_complex

    with_env = SymbolContext(symbol=_class_dump("env", "VAR"), has_env_vars=True)
    assert with_env.is_complex

    with_changes = SymbolContext(symbol=_func_dump("ch"), has_meaningful_changes=True)
    assert with_changes.is_complex


def test_build_symbol_context_only_make_public_not_complex():
    func = _func_dump("my_func")
    action = MakePublicAction(name="my_func", group="config", ts=datetime.now(UTC))
    ctx = build_symbol_context(func, set(), [action])
    assert not ctx.has_meaningful_changes
    assert not ctx.is_complex


def test_build_symbol_context_fix_action_is_complex():
    func = _func_dump("my_func")
    action = FixAction(
        name="my_func", short_sha="abc123", message="fix", ts=datetime.now(UTC)
    )
    ctx = build_symbol_context(func, set(), [action])
    assert ctx.has_meaningful_changes
    assert ctx.is_complex


def test_render_group_index_has_valid_sections():
    group = GroupDump(name="config", symbols=[_func_dump("load"), _func_dump("save")])
    contexts = [SymbolContext(symbol=s) for s in group.symbols]
    content = render_group_index(group, contexts, GroupConfig())

    sections = parse_sections(content, PKG_EXT_TOOL_NAME, MD_CONFIG)
    section_ids = {s.id for s in sections}
    assert "header" in section_ids
    assert "symbols" in section_ids
    assert "symbol_details_header" in section_ids
    assert "load_def" in section_ids
    assert "save_def" in section_ids


def test_render_group_index_includes_docstring():
    group = GroupDump(name="config", symbols=[])
    group_config = GroupConfig(docstring="Configuration utilities.")
    content = render_group_index(group, [], group_config)
    assert "Configuration utilities." in content


def test_generate_docs_creates_index_and_complex_pages(project_config: ProjectConfig):
    api_dump = PublicApiDump(
        pkg_import_name="my_pkg",
        version="1.0.0",
        dumped_at=datetime.now(UTC),
        groups=[
            GroupDump(
                name="config",
                stability=Stability.ga,
                symbols=[
                    _func_dump("simple_func"),
                    _class_dump("EnvClass", env_var="MY_VAR"),
                ],
            )
        ],
    )
    result = generate_docs(api_dump, project_config, {}, [])
    assert isinstance(result, GeneratedDocsOutput)
    assert "config/index.md" in result.path_contents
    assert "config/envclass.md" in result.path_contents
    assert "config/simple_func.md" not in result.path_contents


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
            ClassFieldInfo(
                name="port",
                type_annotation="int",
                default=ParamDefault(value_repr="8080"),
            ),
        ],
    )
    sig = format_signature(cls)
    assert "class MySettings(BaseSettings):" in sig
    assert "host: str = 'localhost'" in sig
    assert "port: int = 8080" in sig


def test_format_signature_exception():
    exc = ExceptionDump(
        name="MyError", module_path="pkg.mod", direct_bases=["ValueError"]
    )
    sig = format_signature(exc)
    assert "class MyError(ValueError):" in sig


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
    doc = "    Summary.\n\n    Details here."
    assert format_docstring(doc) == "Summary.\n\nDetails here."
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
            ClassFieldInfo(name="debug", type_annotation="bool", env_vars=["MY_DEBUG"]),
        ],
    )
    table = render_env_var_table(cls)
    assert "| `MY_HOST` | `host` |" in table
    assert "| `MY_DEBUG` | `debug` |" in table


def test_render_env_var_table_no_vars():
    cls = ClassDump(
        name="Plain", module_path="pkg.mod", fields=[ClassFieldInfo(name="x")]
    )
    assert render_env_var_table(cls) == ""


def test_render_stability_badge():
    func = _func_dump("f")
    ga_group = GroupDump(name="g", stability=Stability.ga, symbols=[])
    exp_group = GroupDump(name="g", stability=Stability.experimental, symbols=[])
    dep_group = GroupDump(name="g", stability=Stability.deprecated, symbols=[])
    assert render_stability_badge(func, ga_group) == ""
    assert "Experimental" in render_stability_badge(func, exp_group)
    assert "Deprecated" in render_stability_badge(func, dep_group)


def test_calculate_source_link():
    doc_path = Path("/repo/docs/config/my_settings.md")
    repo_root = Path("/repo")
    link = calculate_source_link(doc_path, "pkg_ext.config", repo_root, 42)
    assert link == "../../pkg_ext/config.py#L42"
