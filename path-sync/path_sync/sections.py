from __future__ import annotations

from zero_3rdparty.sections import (
    CommentConfig,
    Section,
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
    "has_sections",
    "parse_sections",
    "wrap_in_default_section",
    "extract_sections",
    "replace_sections",
]

TOOL_NAME = "path-sync"
DEFAULT_CONFIG = CommentConfig("#")


def has_sections(content: str) -> bool:
    return _has_sections(content, TOOL_NAME, DEFAULT_CONFIG)


def parse_sections(content: str) -> list[Section]:
    return _parse_sections(content, TOOL_NAME, DEFAULT_CONFIG)


def wrap_in_default_section(content: str) -> str:
    return _wrap_in_default_section(content, TOOL_NAME, DEFAULT_CONFIG)


def extract_sections(content: str) -> dict[str, str]:
    return _extract_sections(content, TOOL_NAME, DEFAULT_CONFIG)


def replace_sections(
    dest_content: str,
    src_sections: dict[str, str],
    skip_sections: list[str] | None = None,
) -> str:
    return _replace_sections(
        dest_content, src_sections, TOOL_NAME, DEFAULT_CONFIG, skip_sections
    )
