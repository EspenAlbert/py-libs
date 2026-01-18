"""MkDocs configuration and file I/O for docs generation."""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

from zero_3rdparty import file_utils
from zero_3rdparty.sections import parse_sections, replace_sections, wrap_section

from pkg_ext.config import PKG_EXT_TOOL_NAME, ROOT_GROUP_NAME
from pkg_ext.generation.docs_constants import MD_CONFIG, ROOT_DIR, YAML_CONFIG

if TYPE_CHECKING:
    from pkg_ext.models.api_dump import PublicApiDump

    from .docs import GeneratedDocsOutput


class MkdocsSection(StrEnum):
    site = "site"
    theme = "theme"
    nav = "nav"
    extensions = "extensions"


def _strip_docs_prefix(content: str) -> str:
    return re.sub(r"\]\(docs/([^)]+)\)", r"](\1)", content)


def copy_readme_as_index(state_dir: Path, docs_dir: Path, pkg_name: str) -> Path:
    index_path = docs_dir / "index.md"
    for name in ("readme.md", "README.md", "Readme.md"):
        readme = state_dir / name
        if readme.exists():
            content = _strip_docs_prefix(readme.read_text())
            file_utils.ensure_parents_write_text(index_path, content)
            return index_path
    file_utils.ensure_parents_write_text(index_path, f"# {pkg_name}\n")
    return index_path


def group_dir_name_for_nav(group_name: str) -> str:
    return ROOT_DIR if group_name == ROOT_GROUP_NAME else group_name


def generate_mkdocs_nav(
    api_dump: PublicApiDump, pkg_import_name: str
) -> list[dict[str, str]]:
    nav: list[dict[str, str]] = [{"Home": "index.md"}]
    groups = sorted(api_dump.groups, key=lambda g: (g.name != ROOT_GROUP_NAME, g.name))
    for group in groups:
        dir_name = group_dir_name_for_nav(group.name)
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
