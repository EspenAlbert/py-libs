"""Generate mkdocs-compatible markdown files from PublicApiDump."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from model_lib import Entity
from pydantic import BaseModel
from zero_3rdparty.humps import depascalize
from zero_3rdparty.sections import slug, wrap_section

from pkg_ext.changelog.actions import ChangelogAction
from pkg_ext.config import (
    PKG_EXT_TOOL_NAME,
    ROOT_GROUP_NAME,
    GroupConfig,
    ProjectConfig,
)
from pkg_ext.generation.docs_constants import MD_CONFIG, ROOT_DIR
from pkg_ext.generation.docs_render import (
    render_inline_symbol,
    render_symbol_page,
)
from pkg_ext.generation.docs_version import (
    MEANINGFUL_CHANGE_ACTIONS,
    build_symbol_changes,
)
from pkg_ext.generation.example_gen import EXAMPLE_NAME_FIELD
from pkg_ext.models.api_dump import ClassDump, GroupDump, PublicApiDump, SymbolDump

logger = logging.getLogger(__name__)


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
    return f"- [`{name}`](#{slug(name)}_def)"


def render_group_index(
    group: GroupDump,
    contexts: list[SymbolContext],
    group_config: GroupConfig,
    changelog_actions: Sequence[ChangelogAction] | None = None,
    *,
    docs_dir: Path | None = None,
    pkg_src_dir: Path | None = None,
    pkg_import_name: str | None = None,
) -> str:
    header = f"# {group.name}\n"
    if group_config.docstring:
        header += f"\n{group_config.docstring}\n"
    sorted_contexts = sorted(contexts, key=lambda c: c.symbol.name)
    symbol_entries = [render_symbol_entry(c) for c in sorted_contexts]
    symbol_list = "\n".join(symbol_entries)

    dir_name = group_dir_name(group)
    index_path = docs_dir / dir_name / "index.md" if docs_dir else None

    inline_sections = []
    for ctx in sorted_contexts:
        if not ctx.is_complex:
            section_id = f"{slug(ctx.symbol.name)}_def"
            inline_content = render_inline_symbol(
                ctx,
                changelog_actions,
                symbol_doc_path=index_path,
                pkg_src_dir=pkg_src_dir,
                pkg_import_name=pkg_import_name,
            )
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


def load_examples_for_group(
    pkg_import_name: str, group_name: str
) -> dict[str, list[Any]]:
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
        path_contents[index_path] = render_group_index(
            group,
            contexts,
            group_config,
            changelog_actions,
            docs_dir=docs_dir,
            pkg_src_dir=pkg_src_dir,
            pkg_import_name=pkg_import_name,
        )

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
                        changelog_actions=changelog_actions,
                        has_env_vars_fn=has_env_vars,
                    )
                else:
                    path_contents[symbol_path] = f"# {ctx.symbol.name}\n"

    return GeneratedDocsOutput(path_contents=path_contents)
