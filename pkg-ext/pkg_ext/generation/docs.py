"""Generate mkdocs-compatible markdown files from PublicApiDump."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

from model_lib.model_base import Entity
from zero_3rdparty.sections import CommentConfig, slug, wrap_section

from pkg_ext.changelog.actions import (
    AdditionalChangeAction,
    BreakingChangeAction,
    ChangelogAction,
    DeprecatedAction,
    FixAction,
    RenameAction,
)
from pkg_ext.config import (
    PKG_EXT_TOOL_NAME,
    ROOT_GROUP_NAME,
    GroupConfig,
    ProjectConfig,
    Stability,
)
from pkg_ext.models.api_dump import (
    ClassDump,
    ClassFieldInfo,
    ExceptionDump,
    FunctionDump,
    GlobalVarDump,
    GroupDump,
    ParamKind,
    PublicApiDump,
    SymbolDump,
    TypeAliasDump,
)

MD_CONFIG = CommentConfig("<!--", " -->")
ROOT_DIR = "_root"

MEANINGFUL_CHANGE_ACTIONS: tuple[type, ...] = (
    FixAction,
    BreakingChangeAction,
    AdditionalChangeAction,
    RenameAction,
    DeprecatedAction,
)


def _format_param(p) -> str:
    """Format a single function parameter."""
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
    # Add / separator after positional-only params
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
    """Format a class field as assignment."""
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
    """Format symbol signature as Python code block content."""
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
    """Format docstring with dedentation, empty string if none."""
    if not docstring:
        return ""
    return dedent(docstring).strip()


def render_env_var_table(symbol: ClassDump) -> str:
    """Render env-var markdown table for BaseSettings subclasses."""
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


def render_stability_badge(symbol: SymbolDump, group: GroupDump) -> str:
    """Render stability badge if non-GA."""
    stability = symbol.stability or group.stability
    if stability == Stability.experimental:
        return "> **Experimental**"
    if stability == Stability.deprecated:
        return "> **Deprecated**"
    return ""


def calculate_source_link(
    symbol_doc_path: Path,
    module_path: str,
    pkg_src_dir: Path,
    line_number: int | None,
) -> str:
    """Calculate relative path from doc file to source file."""
    rel_module = module_path.replace(".", "/") + ".py"
    source_file = pkg_src_dir / rel_module
    rel_path = source_file.relative_to(symbol_doc_path.parent, walk_up=True)
    if line_number:
        return f"{rel_path}#L{line_number}"
    return str(rel_path)


def render_symbol_page(
    ctx: SymbolContext,
    group: GroupDump,
    symbol_doc_path: Path,
    pkg_src_dir: Path,
) -> str:
    """Render full content for a complex symbol's dedicated page."""
    symbol = ctx.symbol
    section_id = f"{slug(symbol.name)}_def"
    type_label = symbol.type.value

    source_link = calculate_source_link(
        symbol_doc_path, symbol.module_path, pkg_src_dir, symbol.line_number
    )
    stability = render_stability_badge(symbol, group)
    sig = format_signature(symbol)
    docstring = format_docstring(symbol.docstring)

    lines = [f"## {type_label}: {symbol.name}", f"- [source]({source_link})"]
    if stability:
        lines.append(stability)
    lines.extend(["", "```python", sig, "```"])
    if docstring:
        lines.extend(["", docstring])

    main_content = wrap_section(
        "\n".join(lines), section_id, PKG_EXT_TOOL_NAME, MD_CONFIG
    )

    parts = [f"# {symbol.name}", "", main_content]

    if isinstance(symbol, ClassDump) and has_env_vars(symbol):
        env_table = render_env_var_table(symbol)
        if env_table:
            parts.extend(["", env_table])

    return "\n".join(parts)


class GeneratedDocsOutput(Entity):
    path_contents: dict[str, str]


@dataclass
class SymbolContext:
    symbol: SymbolDump
    has_examples: bool = False
    has_env_vars: bool = False
    has_meaningful_changes: bool = False

    @property
    def is_complex(self) -> bool:
        return self.has_examples or self.has_env_vars or self.has_meaningful_changes

    @property
    def page_filename(self) -> str:
        return f"{slug(self.symbol.name)}.md"


def group_dir_name(group: GroupDump) -> str:
    return ROOT_DIR if group.name == ROOT_GROUP_NAME else group.name


def has_env_vars(symbol: SymbolDump) -> bool:
    if not isinstance(symbol, ClassDump):
        return False
    if not symbol.fields:
        return False
    return any(f.env_vars for f in symbol.fields)


def build_symbol_context(
    symbol: SymbolDump,
    example_symbols: set[str],
    changelog_actions: list[ChangelogAction],
) -> SymbolContext:
    has_changes = any(
        action.name == symbol.name and isinstance(action, MEANINGFUL_CHANGE_ACTIONS)
        for action in changelog_actions
    )
    return SymbolContext(
        symbol=symbol,
        has_examples=symbol.name in example_symbols,
        has_env_vars=has_env_vars(symbol),
        has_meaningful_changes=has_changes,
    )


def render_symbol_entry(ctx: SymbolContext) -> str:
    name = ctx.symbol.name
    if ctx.is_complex:
        return f"- [{name}](./{slug(name)}.md)"
    return f"- `{name}`"


def render_group_index(
    group: GroupDump, contexts: list[SymbolContext], group_config: GroupConfig
) -> str:
    header = f"# {group.name}\n"
    if group_config.docstring:
        header += f"\n{group_config.docstring}\n"
    sorted_contexts = sorted(contexts, key=lambda c: c.symbol.name)
    symbol_entries = [render_symbol_entry(c) for c in sorted_contexts]
    symbol_list = "\n".join(symbol_entries)

    inline_sections = []
    for ctx in sorted_contexts:
        if not ctx.is_complex:
            section_id = f"{slug(ctx.symbol.name)}_def"
            type_label = ctx.symbol.type.value
            inline_content = f"### {type_label}: `{ctx.symbol.name}`"
            inline_sections.append(
                wrap_section(inline_content, section_id, PKG_EXT_TOOL_NAME, MD_CONFIG)
            )

    parts = [
        wrap_section(header, "header", PKG_EXT_TOOL_NAME, MD_CONFIG),
        "",
        wrap_section(symbol_list, "symbols", PKG_EXT_TOOL_NAME, MD_CONFIG),
    ]
    if inline_sections:
        parts.extend(
            (
                "",
                wrap_section(
                    "## Symbol Details",
                    "symbol_details_header",
                    PKG_EXT_TOOL_NAME,
                    MD_CONFIG,
                ),
                "",
                *inline_sections,
            )
        )

    return "\n".join(parts)


def generate_docs(
    api_dump: PublicApiDump,
    config: ProjectConfig,
    example_symbols: dict[str, set[str]],
    changelog_actions: list[ChangelogAction],
    docs_dir: Path | None = None,
    pkg_src_dir: Path | None = None,
) -> GeneratedDocsOutput:
    path_contents: dict[str, str] = {}

    for group in api_dump.groups:
        dir_name = group_dir_name(group)
        group_examples = example_symbols.get(group.name, set())
        group_config = config.groups.get(group.name, GroupConfig())
        contexts = [
            build_symbol_context(s, group_examples, changelog_actions)
            for s in group.symbols
        ]
        index_path = f"{dir_name}/index.md"
        path_contents[index_path] = render_group_index(group, contexts, group_config)

        for ctx in contexts:
            if ctx.is_complex:
                symbol_path = f"{dir_name}/{ctx.page_filename}"
                if docs_dir and pkg_src_dir:
                    symbol_doc_path = docs_dir / symbol_path
                    path_contents[symbol_path] = render_symbol_page(
                        ctx, group, symbol_doc_path, pkg_src_dir
                    )
                else:
                    path_contents[symbol_path] = f"# {ctx.symbol.name}\n"

    return GeneratedDocsOutput(path_contents=path_contents)
