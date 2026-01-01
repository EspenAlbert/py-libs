from __future__ import annotations

import re
from pathlib import Path

from path_sync.models import (
    DEFAULT_COMMENT_PREFIXES,
    DEFAULT_COMMENT_SUFFIXES,
    HEADER_TEMPLATE,
    HeaderConfig,
)

COMMENT_PREFIXES = DEFAULT_COMMENT_PREFIXES

HEADER_PATTERN = re.compile(r"path-sync copy -n (?P<config_name>[\w-]+)")


def get_header_line(
    extension: str,
    config_name: str,
    config: HeaderConfig | None = None,
) -> str:
    if config:
        prefix = config.comment_prefixes.get(extension, "")
        suffix = config.comment_suffixes.get(extension, "")
    else:
        prefix = DEFAULT_COMMENT_PREFIXES.get(extension, "")
        suffix = DEFAULT_COMMENT_SUFFIXES.get(extension, "")

    if not prefix:
        raise ValueError(f"No comment prefix found for extension: {extension}")
    header_text = HEADER_TEMPLATE.format(config_name=config_name)
    return f"{prefix} {header_text}{suffix}"


def has_header(content: str) -> bool:
    first_line = content.split("\n", 1)[0] if content else ""
    return bool(HEADER_PATTERN.search(first_line))


def get_config_name(content: str) -> str | None:
    first_line = content.split("\n", 1)[0] if content else ""
    if match := HEADER_PATTERN.search(first_line):
        return match.group("config_name")
    return None


def add_header(
    content: str,
    extension: str,
    config_name: str,
    config: HeaderConfig | None = None,
) -> str:
    header = get_header_line(extension, config_name, config)
    return f"{header}\n{content}"


def remove_header(content: str) -> str:
    if not has_header(content):
        return content
    lines = content.split("\n", 1)
    return lines[1] if len(lines) > 1 else ""


def file_get_config_name(path: Path) -> str | None:
    """Read first line and extract config name if present."""
    if not path.exists() or path.suffix not in DEFAULT_COMMENT_PREFIXES:
        return None
    try:
        with path.open() as f:
            first_line = f.readline()
    except (UnicodeDecodeError, OSError):
        return None
    return get_config_name(first_line)


def file_has_header(path: Path, config: HeaderConfig | None = None) -> bool:
    if config and path.suffix not in config.comment_prefixes:
        return False
    return file_get_config_name(path) is not None
