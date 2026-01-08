from __future__ import annotations

from pathlib import Path

from zero_3rdparty.sections import (
    Section,
    get_comment_config,
)
from zero_3rdparty.sections import (
    compare_sections as _compare_sections,
)
from zero_3rdparty.sections import (
    extract_sections as _extract_sections,
)
from zero_3rdparty.sections import (
    has_sections as _has_sections,
)
from zero_3rdparty.sections import (
    parse_sections as _parse_sections,
)
from zero_3rdparty.sections import (
    replace_sections as _replace_sections,
)
from zero_3rdparty.sections import (
    wrap_in_default_section as _wrap_in_default_section,
)

__all__ = [
    "Section",
    "compare_sections",
    "extract_sections",
    "has_sections",
    "parse_sections",
    "replace_sections",
    "wrap_in_default_section",
]

TOOL_NAME = "path-sync"


def has_sections(content: str, path: Path) -> bool:
    return _has_sections(content, TOOL_NAME, get_comment_config(path))


def parse_sections(content: str, path: Path) -> list[Section]:
    return _parse_sections(content, TOOL_NAME, get_comment_config(path))


def wrap_in_default_section(content: str, path: Path) -> str:
    return _wrap_in_default_section(content, TOOL_NAME, get_comment_config(path))


def extract_sections(content: str, path: Path) -> dict[str, str]:
    return _extract_sections(content, TOOL_NAME, get_comment_config(path))


def replace_sections(
    dest_content: str,
    src_sections: dict[str, str],
    path: Path,
    skip_sections: list[str] | None = None,
) -> str:
    return _replace_sections(
        dest_content, src_sections, TOOL_NAME, get_comment_config(path), skip_sections
    )


def compare_sections(
    baseline_content: str,
    current_content: str,
    path: Path,
    skip: set[str] | None = None,
) -> list[str]:
    return _compare_sections(
        baseline_content, current_content, TOOL_NAME, get_comment_config(path), skip
    )
