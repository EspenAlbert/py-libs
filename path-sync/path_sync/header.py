from __future__ import annotations

from pathlib import Path

from path_sync.models import (
    DEFAULT_COMMENT_PREFIXES,
    DEFAULT_COMMENT_SUFFIXES,
    DEFAULT_HEADER_TEXT,
    HeaderConfig,
)

COMMENT_PREFIXES = DEFAULT_COMMENT_PREFIXES


def get_header_line(
    extension: str,
    config: HeaderConfig | None = None,
) -> str:
    if config:
        prefix = config.comment_prefixes.get(extension, "")
        suffix = config.comment_suffixes.get(extension, "")
        header_text = config.header_text
    else:
        prefix = DEFAULT_COMMENT_PREFIXES.get(extension, "")
        suffix = DEFAULT_COMMENT_SUFFIXES.get(extension, "")
        header_text = DEFAULT_HEADER_TEXT

    if not prefix:
        raise ValueError(f"No comment prefix found for extension: {extension}")
    return f"{prefix} {header_text}{suffix}"


def has_header(
    content: str,
    extension: str,
    config: HeaderConfig | None = None,
) -> bool:
    header = get_header_line(extension, config)
    first_line = content.split("\n", 1)[0] if content else ""
    return first_line.strip() == header.strip()


def add_header(
    content: str,
    extension: str,
    config: HeaderConfig | None = None,
) -> str:
    header = get_header_line(extension, config)
    return f"{header}\n{content}"


def remove_header(
    content: str,
    extension: str,
    config: HeaderConfig | None = None,
) -> str:
    if not has_header(content, extension, config):
        return content
    lines = content.split("\n", 1)
    return lines[1] if len(lines) > 1 else ""


def file_has_header(
    path: Path,
    config: HeaderConfig | None = None,
) -> bool:
    if not path.exists():
        return False
    prefixes = config.comment_prefixes if config else DEFAULT_COMMENT_PREFIXES
    if path.suffix not in prefixes:
        return False
    try:
        content = path.read_text()
    except UnicodeDecodeError:
        return False
    return has_header(content, path.suffix, config)
