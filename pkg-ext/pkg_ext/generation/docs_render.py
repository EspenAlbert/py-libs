"""Markdown rendering functions for docs generation."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING, Any

from zero_3rdparty.sections import slug, wrap_section

from pkg_ext.changelog.actions import ChangelogAction
from pkg_ext.config import PKG_EXT_TOOL_NAME, Stability
from pkg_ext.generation.docs_constants import MD_CONFIG
from pkg_ext.generation.docs_version import (
    SymbolChange,
    get_field_since_version,
    get_symbol_since_version,
    get_symbol_stability,
)
from pkg_ext.generation.example_gen import (
    EXAMPLE_BASE_FIELDS,
    EXAMPLE_DESCRIPTION_FIELD,
    EXAMPLE_NAME_FIELD,
)
from pkg_ext.models.api_dump import (
    ClassDump,
    ClassFieldInfo,
    ExceptionDump,
    FunctionDump,
    GlobalVarDump,
    GroupDump,
    ParamKind,
    SymbolDump,
    TypeAliasDump,
)
from pkg_ext.py_format import format_python_string

if TYPE_CHECKING:
    from pkg_ext.generation.docs import SymbolContext


def _format_param(p) -> str:
    parts = [p.name]
    if p.type_annotation:
        parts.append(f": {p.type_annotation}")
    if p.default:
        parts.append(f" = {p.default.value_repr}")
    return "".join(parts)


def _format_function_signature(func: FunctionDump) -> str:
    params: list[str] = []
    saw_keyword_only = False
    for p in func.signature.parameters:
        if p.kind == ParamKind.POSITIONAL_ONLY:
            params.append(_format_param(p))
        elif p.kind == ParamKind.VAR_POSITIONAL:
            params.append(f"*{p.name}")
        elif p.kind == ParamKind.VAR_KEYWORD:
            params.append(f"**{p.name}")
        elif p.kind == ParamKind.KEYWORD_ONLY:
            if not saw_keyword_only:
                if not any(
                    x.kind == ParamKind.VAR_POSITIONAL
                    for x in func.signature.parameters
                ):
                    params.append("*")
                saw_keyword_only = True
            params.append(_format_param(p))
        else:
            params.append(_format_param(p))
    pos_only_count = sum(
        1 for p in func.signature.parameters if p.kind == ParamKind.POSITIONAL_ONLY
    )
    if pos_only_count:
        params.insert(pos_only_count, "/")
    ret = (
        f" -> {func.signature.return_annotation}"
        if func.signature.return_annotation
        else ""
    )
    return f"def {func.name}({', '.join(params)}){ret}:\n    ..."


def _format_field(f: ClassFieldInfo) -> str:
    parts = [f"    {f.name}"]
    if f.type_annotation:
        parts.append(f": {f.type_annotation}")
    if f.default:
        parts.append(f" = {f.default.value_repr}")
    return "".join(parts)


def _format_class_signature(cls: ClassDump) -> str:
    bases = f"({', '.join(cls.direct_bases)})" if cls.direct_bases else ""
    header = f"class {cls.name}{bases}:"
    if not cls.fields:
        return f"{header}\n    ..."
    field_lines = [_format_field(f) for f in cls.fields if not f.is_computed]
    return f"{header}\n" + "\n".join(field_lines)


def _format_exception_signature(exc: ExceptionDump) -> str:
    bases = f"({', '.join(exc.direct_bases)})" if exc.direct_bases else ""
    return f"class {exc.name}{bases}:\n    ..."


def format_signature(symbol: SymbolDump) -> str:
    match symbol:
        case FunctionDump():
            return _format_function_signature(symbol)
        case ClassDump():
            return _format_class_signature(symbol)
        case ExceptionDump():
            return _format_exception_signature(symbol)
        case TypeAliasDump():
            return f"{symbol.name} = {symbol.alias_target}"
        case GlobalVarDump():
            ann = f": {symbol.annotation}" if symbol.annotation else ""
            val = f" = {symbol.value_repr}" if symbol.value_repr else ""
            return f"{symbol.name}{ann}{val}"
    return f"# {symbol.name}"


def format_docstring(docstring: str) -> str:
    if not docstring:
        return ""
    return dedent(docstring).strip()


def render_env_var_table(symbol: ClassDump) -> str:
    rows: list[str] = []
    for f in symbol.fields or []:
        for env_var in f.env_vars or []:
            default = f.default.value_repr if f.default else "-"
            rows.append(
                f"| `{env_var}` | `{f.name}` | {f.type_annotation or '-'} | {default} |"
            )
    if not rows:
        return ""
    header = "### Environment Variables\n\n| Variable | Field | Type | Default |\n|----------|-------|------|---------|"
    return f"{header}\n" + "\n".join(rows)


def should_show_field_table(
    fields: list[ClassFieldInfo] | None,
    field_versions: dict[str, str] | None = None,
) -> bool:
    if not fields:
        return False
    visible = [f for f in fields if not f.is_computed]
    if any(f.deprecated or f.description for f in visible):
        return True
    if field_versions and any(field_versions.get(f.name) for f in visible):
        return True
    return False


def render_field_table(
    fields: list[ClassFieldInfo] | None,
    field_versions: dict[str, str] | None = None,
) -> str:
    if not fields:
        return ""
    visible = [f for f in fields if not f.is_computed]
    if not visible:
        return ""

    has_deprecated = any(f.deprecated for f in visible)
    has_description = any(f.description for f in visible)
    has_since = field_versions and any(field_versions.get(f.name) for f in visible)

    cols = ["Field", "Type", "Default"]
    if has_since:
        cols.append("Since")
    if has_deprecated:
        cols.append("Deprecated")
    if has_description:
        cols.append("Description")

    header = "| " + " | ".join(cols) + " |"
    separator = "|" + "|".join("---" for _ in cols) + "|"

    rows = []
    for f in visible:
        default = f"`{f.default.value_repr}`" if f.default else "-"
        row = [f.name, f"`{f.type_annotation}`" if f.type_annotation else "-", default]
        if has_since and field_versions:
            row.append(field_versions.get(f.name) or "-")
        if has_deprecated:
            row.append(f.deprecated or "-")
        if has_description:
            row.append((f.description or "-").replace("|", "\\|"))
        rows.append("| " + " | ".join(row) + " |")

    return "\n".join([header, separator, *rows])


def _build_field_versions(
    symbol_name: str,
    fields: list[ClassFieldInfo] | None,
    changelog_actions: Sequence[ChangelogAction],
) -> dict[str, str]:
    if not fields:
        return {}
    return {
        f.name: v
        for f in fields
        if not f.is_computed
        and (v := get_field_since_version(symbol_name, f.name, changelog_actions))
    }


def render_since_badge(version: str | None) -> str:
    return f"> **Since:** {version}" if version else ""


def render_stability_badge(
    symbol_name: str,
    group_name: str,
    changelog_actions: Sequence[ChangelogAction],
) -> str:
    stability = get_symbol_stability(symbol_name, group_name, changelog_actions)
    if stability == Stability.experimental:
        return "> **Experimental**"
    if stability == Stability.deprecated:
        return "> **Deprecated**"
    return ""


def calculate_source_link(
    symbol_doc_path: Path,
    module_path: str,
    pkg_src_dir: Path,
    pkg_import_name: str,
    line_number: int | None,
) -> str:
    rel_module = module_path.replace(".", "/") + ".py"
    source_file = pkg_src_dir / pkg_import_name / rel_module
    rel_path = source_file.relative_to(symbol_doc_path.parent, walk_up=True)
    if line_number:
        return f"{rel_path}#L{line_number}"
    return str(rel_path)


def render_inline_symbol(
    ctx: SymbolContext,
    changelog_actions: Sequence[ChangelogAction] | None = None,
    *,
    symbol_doc_path: Path | None = None,
    pkg_src_dir: Path | None = None,
    pkg_import_name: str | None = None,
) -> str:
    symbol = ctx.symbol
    type_label = symbol.type.value
    sig = format_signature(symbol)
    changelog_actions = changelog_actions or []

    since_version = get_symbol_since_version(symbol.name, changelog_actions)
    since_badge = render_since_badge(since_version)

    lines = [f"### {type_label}: `{symbol.name}`"]
    if symbol_doc_path and pkg_src_dir and pkg_import_name:
        source_link = calculate_source_link(
            symbol_doc_path,
            symbol.module_path,
            pkg_src_dir,
            pkg_import_name,
            symbol.line_number,
        )
        lines.append(f"- [source]({source_link})")
    if since_badge:
        lines.append(since_badge)
    lines.extend(["", "```python", sig, "```"])

    docstring = format_docstring(symbol.docstring)
    if docstring:
        lines.extend(["", docstring])

    if isinstance(symbol, ClassDump) and symbol.fields:
        field_versions = _build_field_versions(
            symbol.name, symbol.fields, changelog_actions
        )
        if should_show_field_table(symbol.fields, field_versions):
            if table := render_field_table(symbol.fields, field_versions):
                lines.extend(["", table])

    return "\n".join(lines)


def _render_symbol_main_section(
    symbol: SymbolDump,
    group: GroupDump,
    source_link: str,
    changelog_actions: Sequence[ChangelogAction],
) -> str:
    section_id = f"{slug(symbol.name)}_def"
    type_label = symbol.type.value
    stability = render_stability_badge(symbol.name, group.name, changelog_actions)
    since_badge = render_since_badge(
        get_symbol_since_version(symbol.name, changelog_actions)
    )
    sig = format_signature(symbol)
    docstring = format_docstring(symbol.docstring)

    lines = [f"## {type_label}: {symbol.name}", f"- [source]({source_link})"]
    if stability:
        lines.append(stability)
    if since_badge:
        lines.append(since_badge)
    lines.extend(["", "```python", sig, "```"])
    if docstring:
        lines.extend(["", docstring])
    return wrap_section("\n".join(lines), section_id, PKG_EXT_TOOL_NAME, MD_CONFIG)


def render_symbol_page(
    ctx: SymbolContext,
    group: GroupDump,
    symbol_doc_path: Path,
    pkg_src_dir: Path,
    pkg_import_name: str,
    examples: list[Any] | None = None,
    changes: list[SymbolChange] | None = None,
    changelog_actions: Sequence[ChangelogAction] | None = None,
    *,
    has_env_vars_fn=None,
) -> str:
    symbol = ctx.symbol
    changelog_actions = changelog_actions or []

    source_link = calculate_source_link(
        symbol_doc_path,
        symbol.module_path,
        pkg_src_dir,
        pkg_import_name,
        symbol.line_number,
    )
    main_content = _render_symbol_main_section(
        symbol, group, source_link, changelog_actions
    )
    parts = [f"# {symbol.name}", "", main_content]

    if has_env_vars_fn and isinstance(symbol, ClassDump) and has_env_vars_fn(symbol):
        if env_table := render_env_var_table(symbol):
            parts.extend(["", env_table])

    if isinstance(symbol, ClassDump) and symbol.fields:
        field_versions = _build_field_versions(
            symbol.name, symbol.fields, changelog_actions
        )
        if should_show_field_table(symbol.fields, field_versions):
            if table := render_field_table(symbol.fields, field_versions):
                parts.extend(["", "### Fields", "", table])

    for ex in examples or []:
        parts.extend(["", render_example_section(ex, symbol, pkg_import_name)])

    if changes:
        parts.extend(["", render_changes_section(changes, symbol.name)])

    return "\n".join(parts)


def render_changes_section(changes: list[SymbolChange], symbol_name: str) -> str:
    if not changes:
        return ""
    section_id = f"{slug(symbol_name)}_changes"
    lines = [
        "### Changes",
        "",
        "| Version | Change |",
        "|---------|--------|",
    ]
    for c in changes:
        lines.append(f"| {c.version} | {c.description} |")
    return wrap_section("\n".join(lines), section_id, PKG_EXT_TOOL_NAME, MD_CONFIG)


def _format_example_value(value: Any) -> str:
    if isinstance(value, str):
        if "\n" in value:
            return f'"""\\\n{value}"""'
        return repr(value)
    if isinstance(value, datetime):
        return f"datetime({value.year}, {value.month}, {value.day})"
    return repr(value)


def render_example_section(
    example: Any, symbol: SymbolDump, pkg_import_name: str
) -> str:
    example_name = getattr(example, EXAMPLE_NAME_FIELD, "")
    description = getattr(example, EXAMPLE_DESCRIPTION_FIELD, "")
    section_id = f"{slug(symbol.name)}_example_{slug(example_name)}"

    fields = {
        k: v for k, v in example.model_dump().items() if k not in EXAMPLE_BASE_FIELDS
    }

    if isinstance(symbol, FunctionDump):
        args = ", ".join(f"{k}={_format_example_value(v)}" for k, v in fields.items())
        code = f"result = {symbol.name}({args})"
    elif isinstance(symbol, ClassDump):
        args = ", ".join(f"{k}={_format_example_value(v)}" for k, v in fields.items())
        code = f"instance = {symbol.name}({args})"
    else:
        code = f"# {symbol.name} example"

    formatted_code = format_python_string(code)

    lines = [f"### Example: {example_name}"]
    if description:
        lines.append(description)
    lines.extend(["", "```python", formatted_code, "```"])

    return wrap_section("\n".join(lines), section_id, PKG_EXT_TOOL_NAME, MD_CONFIG)
