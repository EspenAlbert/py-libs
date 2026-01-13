"""Generate mkdocs-compatible markdown files from PublicApiDump."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from textwrap import dedent
from typing import Any

from model_lib import utc_datetime
from model_lib.model_base import Entity, Event
from pydantic import BaseModel
from zero_3rdparty import file_utils
from zero_3rdparty.humps import depascalize
from zero_3rdparty.sections import (
    CommentConfig,
    parse_sections,
    replace_sections,
    slug,
    wrap_section,
)

from pkg_ext.changelog.actions import (
    AdditionalChangeAction,
    BreakingChangeAction,
    ChangelogAction,
    DeprecatedAction,
    FixAction,
    MakePublicAction,
    ReleaseAction,
    RenameAction,
)
from pkg_ext.config import (
    PKG_EXT_TOOL_NAME,
    ROOT_GROUP_NAME,
    GroupConfig,
    ProjectConfig,
    Stability,
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
    PublicApiDump,
    SymbolDump,
    TypeAliasDump,
)
from pkg_ext.py_format import format_python_string

logger = logging.getLogger(__name__)
MD_CONFIG = CommentConfig("<!--", " -->")
YAML_CONFIG = CommentConfig("#")
ROOT_DIR = "_root"


class MkdocsSection(StrEnum):
    site = "site"
    theme = "theme"
    nav = "nav"
    extensions = "extensions"


MEANINGFUL_CHANGE_ACTIONS: tuple[type, ...] = (
    FixAction,
    BreakingChangeAction,
    AdditionalChangeAction,
    RenameAction,
    DeprecatedAction,
)

UNRELEASED_VERSION = "unreleased"


class SymbolChange(Event):
    version: str
    description: str
    ts: utc_datetime


def _action_description(action: ChangelogAction) -> str:
    match action:
        case MakePublicAction():
            return "Made public"
        case FixAction():
            return action.changelog_message or action.message
        case BreakingChangeAction():
            return action.details
        case AdditionalChangeAction():
            return action.details
        case RenameAction():
            base = f"Renamed from `{action.old_name}`"
            return base
        case DeprecatedAction():
            if action.replacement:
                return f"Deprecated, use `{action.replacement}` instead"
            return "Deprecated"
    return ""


def build_symbol_changes(
    symbol_name: str, changelog_actions: Sequence[ChangelogAction]
) -> list[SymbolChange]:
    """Build change history for a symbol with version tracking."""
    current_version = UNRELEASED_VERSION
    changes: list[SymbolChange] = []
    for action in sorted(changelog_actions):
        if isinstance(action, ReleaseAction):
            current_version = action.name
            continue
        if action.name != symbol_name:
            continue
        if isinstance(action, MakePublicAction):
            changes.append(
                SymbolChange(
                    version=current_version, description="Made public", ts=action.ts
                )
            )
        elif isinstance(action, MEANINGFUL_CHANGE_ACTIONS):
            desc = _action_description(action)
            if desc:
                changes.append(
                    SymbolChange(
                        version=current_version, description=desc, ts=action.ts
                    )
                )
    return sorted(
        changes, key=lambda c: (c.version != UNRELEASED_VERSION, c.ts), reverse=True
    )


def load_examples_for_group(
    pkg_import_name: str, group_name: str
) -> dict[str, list[Any]]:
    """Load example instances from {group}_examples.py, grouped by symbol name."""
    module_name = f"{pkg_import_name}.{group_name}_examples"
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        logger.debug(f"No examples module found: {module_name}")
        return {}

    result: dict[str, list[Any]] = {}
    for obj in vars(module).values():
        if not isinstance(obj, BaseModel):
            continue
        cls_name = type(obj).__name__
        if not cls_name.endswith("Example") or cls_name == "Example":
            continue
        symbol_name = depascalize(cls_name.removesuffix("Example"))
        result.setdefault(symbol_name, []).append(obj)

    for examples in result.values():
        examples.sort(key=lambda e: getattr(e, EXAMPLE_NAME_FIELD, ""))
    return result


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
    """Render single example section with code snippet."""
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


def render_changes_section(changes: list[SymbolChange], symbol_name: str) -> str:
    """Render changes table sorted by version descending."""
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
    pkg_import_name: str,
    examples: list[Any] | None = None,
    changes: list[SymbolChange] | None = None,
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

    for ex in examples or []:
        parts.extend(["", render_example_section(ex, symbol, pkg_import_name)])

    if changes:
        parts.extend(["", render_changes_section(changes, symbol.name)])

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
    load_examples: bool = False,
) -> GeneratedDocsOutput:
    path_contents: dict[str, str] = {}
    pkg_import_name = api_dump.pkg_import_name

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

        loaded_examples: dict[str, list[Any]] = {}
        if load_examples:
            loaded_examples = load_examples_for_group(pkg_import_name, group.name)

        for ctx in contexts:
            if ctx.is_complex:
                symbol_path = f"{dir_name}/{ctx.page_filename}"
                if docs_dir and pkg_src_dir:
                    symbol_doc_path = docs_dir / symbol_path
                    symbol_examples = loaded_examples.get(ctx.symbol.name, [])
                    symbol_changes = build_symbol_changes(
                        ctx.symbol.name, changelog_actions
                    )
                    path_contents[symbol_path] = render_symbol_page(
                        ctx,
                        group,
                        symbol_doc_path,
                        pkg_src_dir,
                        pkg_import_name,
                        examples=symbol_examples,
                        changes=symbol_changes,
                    )
                else:
                    path_contents[symbol_path] = f"# {ctx.symbol.name}\n"

    return GeneratedDocsOutput(path_contents=path_contents)


def copy_readme_as_index(state_dir: Path, docs_dir: Path, pkg_name: str) -> Path:
    """Copy readme.md to docs/index.md or generate minimal one."""
    index_path = docs_dir / "index.md"
    for name in ("readme.md", "README.md", "Readme.md"):
        readme = state_dir / name
        if readme.exists():
            file_utils.ensure_parents_write_text(index_path, readme.read_text())
            return index_path
    file_utils.ensure_parents_write_text(index_path, f"# {pkg_name}\n")
    return index_path


def generate_mkdocs_nav(
    api_dump: PublicApiDump, pkg_import_name: str
) -> list[dict[str, str]]:
    """Generate mkdocs nav structure from API dump."""
    nav: list[dict[str, str]] = [{"Home": "index.md"}]
    groups = sorted(api_dump.groups, key=lambda g: (g.name != ROOT_GROUP_NAME, g.name))
    for group in groups:
        dir_name = group_dir_name(group)
        label = pkg_import_name if group.name == ROOT_GROUP_NAME else group.name
        nav.append({label: f"{dir_name}/index.md"})
    return nav


def _render_nav_yaml(nav: list[dict[str, str]]) -> str:
    lines = ["nav:"]
    for item in nav:
        for label, path in item.items():
            lines.append(f"  - {label}: {path}")
    return "\n".join(lines)


def _mkdocs_section_content(
    section: MkdocsSection, pkg_import_name: str, nav: list[dict[str, str]]
) -> str:
    match section:
        case MkdocsSection.site:
            return f"site_name: {pkg_import_name}"
        case MkdocsSection.theme:
            return dedent("""\
                theme:
                  name: material
                  features:
                    - navigation.tabs
                    - navigation.sections""").rstrip()
        case MkdocsSection.nav:
            return _render_nav_yaml(nav)
        case MkdocsSection.extensions:
            return dedent("""\
                markdown_extensions:
                  - pymdownx.highlight:
                      anchor_linenums: true
                  - pymdownx.superfences
                  - admonition""").rstrip()


def write_mkdocs_yml(
    mkdocs_path: Path,
    pkg_import_name: str,
    nav: list[dict[str, str]],
    skip_sections: tuple[str, ...] = (),
) -> None:
    """Write or update mkdocs.yml with section markers."""
    skip_set = set(skip_sections)
    sections_to_write = [s for s in MkdocsSection if s not in skip_set]

    if mkdocs_path.exists():
        existing = mkdocs_path.read_text()
        src_sections = {
            s.value: _mkdocs_section_content(s, pkg_import_name, nav)
            for s in sections_to_write
        }
        new_content = replace_sections(
            existing, src_sections, PKG_EXT_TOOL_NAME, YAML_CONFIG
        )
        mkdocs_path.write_text(new_content)
    else:
        lines = []
        for section in sections_to_write:
            content = _mkdocs_section_content(section, pkg_import_name, nav)
            wrapped = wrap_section(
                content, section.value, PKG_EXT_TOOL_NAME, YAML_CONFIG
            )
            lines.append(wrapped)
        file_utils.ensure_parents_write_text(mkdocs_path, "\n\n".join(lines) + "\n")


def write_docs_files(output: GeneratedDocsOutput, docs_dir: Path) -> int:
    """Write generated doc files, preserving user content in existing files."""
    count = 0
    for rel_path, content in output.path_contents.items():
        path = docs_dir / rel_path
        if path.exists():
            existing = path.read_text()
            src_sections = {
                s.id: s.content
                for s in parse_sections(content, PKG_EXT_TOOL_NAME, MD_CONFIG)
            }
            merged = replace_sections(
                existing, src_sections, PKG_EXT_TOOL_NAME, MD_CONFIG
            )
            path.write_text(merged)
        else:
            file_utils.ensure_parents_write_text(path, content)
        count += 1
    return count
