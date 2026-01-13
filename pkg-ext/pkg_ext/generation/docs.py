"""Generate mkdocs-compatible markdown files from PublicApiDump."""

from __future__ import annotations

from dataclasses import dataclass

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
from pkg_ext.config import ROOT_GROUP_NAME
from pkg_ext.models.api_dump import ClassDump, GroupDump, PublicApiDump, SymbolDump

TOOL_NAME = "pkg-ext"
MD_CONFIG = CommentConfig("<!--", " -->")
ROOT_DIR = "_root"

MEANINGFUL_CHANGE_ACTIONS: tuple[type, ...] = (
    FixAction,
    BreakingChangeAction,
    AdditionalChangeAction,
    RenameAction,
    DeprecatedAction,
)


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


def render_group_index(group: GroupDump, contexts: list[SymbolContext]) -> str:
    header = f"# {group.name}\n"
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
                wrap_section(inline_content, section_id, TOOL_NAME, MD_CONFIG)
            )

    parts = [
        wrap_section(header, "header", TOOL_NAME, MD_CONFIG),
        "",
        wrap_section(symbol_list, "symbols", TOOL_NAME, MD_CONFIG),
    ]
    if inline_sections:
        parts.extend(
            (
                "",
                wrap_section(
                    "## Symbol Details", "symbol_details_header", TOOL_NAME, MD_CONFIG
                ),
                "",
                *inline_sections,
            )
        )

    return "\n".join(parts)


def generate_docs(
    api_dump: PublicApiDump,
    example_symbols: dict[str, set[str]],
    changelog_actions: list[ChangelogAction],
) -> GeneratedDocsOutput:
    path_contents: dict[str, str] = {}

    for group in api_dump.groups:
        dir_name = group_dir_name(group)
        group_examples = example_symbols.get(group.name, set())
        contexts = [
            build_symbol_context(s, group_examples, changelog_actions)
            for s in group.symbols
        ]
        index_path = f"{dir_name}/index.md"
        path_contents[index_path] = render_group_index(group, contexts)

        for ctx in contexts:
            if ctx.is_complex:
                symbol_path = f"{dir_name}/{ctx.page_filename}"
                path_contents[symbol_path] = f"# {ctx.symbol.name}\n"

    return GeneratedDocsOutput(path_contents=path_contents)
