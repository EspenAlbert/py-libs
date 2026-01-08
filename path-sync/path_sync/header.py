from __future__ import annotations

import re
from pathlib import Path

from zero_3rdparty.sections import CommentConfig, get_comment_config

from path_sync.models import HEADER_TEMPLATE, HeaderConfig

HEADER_PATTERN = re.compile(r"path-sync copy -n (?P<config_name>[\w-]+)")


def _resolve_comment_config(path: Path, config: HeaderConfig | None) -> CommentConfig:
    if config:
        ext = path.suffix
        prefix = config.comment_prefixes.get(ext)
        suffix = config.comment_suffixes.get(ext, "")
        if prefix:
            return CommentConfig(prefix, suffix)
    return get_comment_config(path)


def get_comment_prefix(path: Path, config: HeaderConfig | None = None) -> str:
    return _resolve_comment_config(path, config).prefix


def get_comment_suffix(path: Path, config: HeaderConfig | None = None) -> str:
    return _resolve_comment_config(path, config).suffix


def get_header_line(
    path: Path, config_name: str, config: HeaderConfig | None = None
) -> str:
    cc = _resolve_comment_config(path, config)
    header_text = HEADER_TEMPLATE.format(config_name=config_name)
    return f"{cc.prefix} {header_text}{cc.suffix}"


def has_header(content: str) -> bool:
    first_line = content.split("\n", 1)[0] if content else ""
    return bool(HEADER_PATTERN.search(first_line))


def get_config_name(content: str) -> str | None:
    first_line = content.split("\n", 1)[0] if content else ""
    if match := HEADER_PATTERN.search(first_line):
        return match.group("config_name")
    return None


def add_header(
    content: str, path: Path, config_name: str, config: HeaderConfig | None = None
) -> str:
    header = get_header_line(path, config_name, config)
    return f"{header}\n{content}"


def remove_header(content: str) -> str:
    if not has_header(content):
        return content
    lines = content.split("\n", 1)
    return lines[1] if len(lines) > 1 else ""


def has_known_comment_prefix(path: Path) -> bool:
    try:
        get_comment_config(path)
        return True
    except ValueError:
        return False


def file_get_config_name(path: Path) -> str | None:
    if not path.exists() or not has_known_comment_prefix(path):
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
