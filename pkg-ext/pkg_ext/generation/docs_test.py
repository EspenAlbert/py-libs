from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel
from zero_3rdparty.sections import parse_sections

from pkg_ext.changelog.actions import (
    AdditionalChangeAction,
    DeprecatedAction,
    FixAction,
    MakePublicAction,
    ReleaseAction,
    RenameAction,
    StabilityTarget,
)
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
    UNRELEASED_VERSION,
    GeneratedDocsOutput,
    SymbolChange,
    SymbolContext,
    build_symbol_changes,
    build_symbol_context,
    calculate_source_link,
    find_release_version,
    format_docstring,
    format_signature,
    generate_docs,
    get_field_since_version,
    get_symbol_since_version,
    group_dir_name,
    has_env_vars,
    render_changes_section,
    render_env_var_table,
    render_example_section,
    render_field_table,
    render_group_index,
    render_inline_symbol,
    render_stability_badge,
    should_show_field_table,
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
    assert "[`load`](#load_def)" in content
    assert "[`save`](#save_def)" in content


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
    link = calculate_source_link(doc_path, "config", repo_root, "pkg_ext", 42)
    assert link == "../../pkg_ext/config.py#L42"


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
    assert changes[0].description == "fix bug"
    assert changes[1].description == "Made public"


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


def test_render_changes_section():
    changes = [
        SymbolChange(
            version="1.1.0",
            description="Added param",
            ts=datetime(2025, 2, 1, tzinfo=UTC),
        ),
        SymbolChange(
            version="1.0.0",
            description="Made public",
            ts=datetime(2025, 1, 1, tzinfo=UTC),
        ),
    ]
    content = render_changes_section(changes, "my_func")
    assert "| 1.1.0 | Added param |" in content
    assert "| 1.0.0 | Made public |" in content


class ParseExample(BaseModel):
    example_name: str = "basic"
    example_description_md: str = "Parse a string"
    data: str = "hello"


def test_render_example_section_function():
    func = _func_dump("parse")
    example = ParseExample(
        example_name="basic", example_description_md="Test parse", data="test"
    )
    content = render_example_section(example, func, "my_pkg")
    assert "### Example: basic" in content
    assert "Test parse" in content
    assert "result = parse(data=" in content


def test_render_example_section_class():
    cls = _class_dump("Settings")
    example = ParseExample(example_name="default", data="cfg")
    content = render_example_section(example, cls, "my_pkg")
    assert "### Example: default" in content
    assert "instance = Settings(data=" in content


def test_copy_readme_as_index(tmp_path: Path):
    from pkg_ext.generation.docs import copy_readme_as_index

    state_dir = tmp_path / "pkg"
    state_dir.mkdir()
    (state_dir / "readme.md").write_text("# My Package\n\nDescription here.")
    docs_dir = tmp_path / "docs"
    index = copy_readme_as_index(state_dir, docs_dir, "my_pkg")
    assert index.exists()
    assert "# My Package" in index.read_text()


def test_copy_readme_fallback(tmp_path: Path):
    from pkg_ext.generation.docs import copy_readme_as_index

    state_dir = tmp_path / "pkg"
    state_dir.mkdir()
    docs_dir = tmp_path / "docs"
    index = copy_readme_as_index(state_dir, docs_dir, "my_pkg")
    assert index.read_text() == "# my_pkg\n"


def test_generate_mkdocs_nav():
    from pkg_ext.generation.docs import generate_mkdocs_nav

    api_dump = PublicApiDump(
        pkg_import_name="my_pkg",
        version="1.0.0",
        dumped_at=datetime.now(UTC),
        groups=[
            GroupDump(name=ROOT_GROUP_NAME, symbols=[]),
            GroupDump(name="config", symbols=[]),
        ],
    )
    nav = generate_mkdocs_nav(api_dump, "my_pkg")
    assert nav[0] == {"Home": "index.md"}
    assert {"my_pkg": "_root/index.md"} in nav
    assert {"config": "config/index.md"} in nav


def test_write_mkdocs_yml_creates_new(tmp_path: Path):
    from pkg_ext.generation.docs import MkdocsSection, write_mkdocs_yml

    mkdocs_path = tmp_path / "mkdocs.yml"
    nav = [{"Home": "index.md"}, {"config": "config/index.md"}]
    write_mkdocs_yml(mkdocs_path, "my_pkg", nav)
    content = mkdocs_path.read_text()
    assert "site_name: my_pkg" in content
    assert "nav:" in content
    assert "config: config/index.md" in content
    for section in MkdocsSection:
        assert f"DO_NOT_EDIT: pkg-ext {section.value}" in content


def test_write_mkdocs_yml_honors_skip_sections(tmp_path: Path):
    from pkg_ext.generation.docs import write_mkdocs_yml

    mkdocs_path = tmp_path / "mkdocs.yml"
    nav = [{"Home": "index.md"}]
    write_mkdocs_yml(mkdocs_path, "my_pkg", nav, skip_sections=("theme", "extensions"))
    content = mkdocs_path.read_text()
    assert "site_name:" in content
    assert "nav:" in content
    assert "theme:" not in content
    assert "markdown_extensions:" not in content


def test_write_docs_files_idempotent(tmp_path: Path, project_config: ProjectConfig):
    from pkg_ext.generation.docs import GeneratedDocsOutput, write_docs_files

    docs_dir = tmp_path / "docs"
    output = GeneratedDocsOutput(path_contents={"config/index.md": "# Config\n"})
    count1 = write_docs_files(output, docs_dir)
    content1 = (docs_dir / "config/index.md").read_text()
    count2 = write_docs_files(output, docs_dir)
    content2 = (docs_dir / "config/index.md").read_text()
    assert count1 == count2 == 1
    assert content1 == content2


def _class_with_fields(
    name: str,
    deprecated: str | None = None,
    description: str | None = None,
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


def test_should_show_field_table_no_metadata():
    cls = _class_with_fields("Config")
    assert not should_show_field_table(cls.fields)


def test_should_show_field_table_with_deprecated():
    cls = _class_with_fields("Config", deprecated="Use validation_mode instead")
    assert should_show_field_table(cls.fields)


def test_should_show_field_table_with_description():
    cls = _class_with_fields("Config", description="Enable strict mode")
    assert should_show_field_table(cls.fields)


def test_render_field_table_with_deprecated():
    cls = _class_with_fields("Config", deprecated="Use validation_mode instead")
    table = render_field_table(cls.fields)
    assert "| Field | Type | Default | Deprecated |" in table
    assert "| timeout | `int` | `30` | - |" in table
    assert "Use validation_mode instead" in table


def test_render_field_table_with_description():
    cls = _class_with_fields("Config", description="Enable strict mode")
    table = render_field_table(cls.fields)
    assert "| Field | Type | Default | Description |" in table
    assert "Enable strict mode" in table


def test_render_field_table_escapes_pipes():
    cls = ClassDump(
        name="Config",
        module_path="mod",
        fields=[
            ClassFieldInfo(
                name="pattern",
                type_annotation="str",
                description="Use | for OR",
            ),
        ],
    )
    table = render_field_table(cls.fields)
    assert "Use \\| for OR" in table


def test_render_inline_symbol_function():
    func = _func_dump("load")
    ctx = SymbolContext(symbol=func)
    content = render_inline_symbol(ctx)
    assert "### function: `load`" in content
    assert "```python" in content
    assert "def load(" in content


def test_render_inline_symbol_class_no_table():
    cls = _class_with_fields("CopyOptions")
    ctx = SymbolContext(symbol=cls)
    content = render_inline_symbol(ctx)
    assert "### class: `CopyOptions`" in content
    assert "```python" in content
    assert "class CopyOptions:" in content
    assert "timeout: int = 30" in content
    assert "| Field |" not in content  # No table when no metadata


def test_render_inline_symbol_class_with_table():
    cls = _class_with_fields("Config", deprecated="Use new_strict")
    ctx = SymbolContext(symbol=cls)
    content = render_inline_symbol(ctx)
    assert "### class: `Config`" in content
    assert "| Field | Type | Default | Deprecated |" in content


def test_render_inline_symbol_with_docstring():
    func = FunctionDump(
        name="parse",
        module_path="mod",
        signature=CallableSignature(),
        docstring="    Parse input data.\n\n    Returns parsed result.",
    )
    ctx = SymbolContext(symbol=func)
    content = render_inline_symbol(ctx)
    assert "### function: `parse`" in content
    assert "```python" in content
    assert "Parse input data." in content
    assert "Returns parsed result." in content


def test_render_group_index_includes_signatures():
    cls = _class_with_fields("SimpleClass")
    group = GroupDump(name="utils", symbols=[cls])
    contexts = [SymbolContext(symbol=cls)]
    content = render_group_index(group, contexts, GroupConfig())
    assert "class SimpleClass:" in content
    assert "timeout: int = 30" in content


def test_find_release_version_found():
    actions = [
        ReleaseAction(
            name="1.0.0", old_version="0.0.0", ts=datetime(2025, 1, 10, tzinfo=UTC)
        ),
    ]
    version = find_release_version(datetime(2025, 1, 5, tzinfo=UTC), actions)
    assert version == "1.0.0"


def test_find_release_version_not_found():
    actions = [
        ReleaseAction(
            name="1.0.0", old_version="0.0.0", ts=datetime(2025, 1, 1, tzinfo=UTC)
        ),
    ]
    version = find_release_version(datetime(2025, 2, 1, tzinfo=UTC), actions)
    assert version is None


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


def test_get_symbol_since_version_not_found():
    actions = [
        ReleaseAction(
            name="1.0.0", old_version="0.0.0", ts=datetime(2025, 1, 10, tzinfo=UTC)
        ),
    ]
    assert get_symbol_since_version("unknown", actions) is None


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


def test_should_show_field_table_with_since_version():
    cls = _class_with_fields("Config")
    field_versions = {"timeout": "1.0.0"}
    assert should_show_field_table(cls.fields, field_versions)


def test_render_field_table_with_since_column():
    cls = _class_with_fields("Config")
    field_versions = {"timeout": "1.0.0"}
    table = render_field_table(cls.fields, field_versions)
    assert "| Field | Type | Default | Since |" in table
    assert "| 1.0.0 |" in table


def test_render_inline_symbol_shows_since_badge():
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


def test_render_inline_symbol_with_source_link(tmp_path: Path):
    func = FunctionDump(
        name="parse",
        module_path="config",
        signature=CallableSignature(),
        line_number=42,
    )
    ctx = SymbolContext(symbol=func)
    docs_dir = tmp_path / "docs"
    pkg_src = tmp_path
    content = render_inline_symbol(
        ctx,
        symbol_doc_path=docs_dir / "config/index.md",
        pkg_src_dir=pkg_src,
        pkg_import_name="my_pkg",
    )
    assert "- [source](../../my_pkg/config.py#L42)" in content


def test_render_inline_symbol_no_source_link_when_params_missing():
    func = _func_dump("parse")
    ctx = SymbolContext(symbol=func)
    content = render_inline_symbol(ctx)
    assert "[source]" not in content
