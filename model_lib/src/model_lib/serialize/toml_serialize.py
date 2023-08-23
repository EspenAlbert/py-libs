from __future__ import annotations

import logging
import re
import sys
from contextlib import suppress
from dataclasses import dataclass
from textwrap import indent
from typing import Any, Callable, Union

logger = logging.getLogger(__name__)


def raise_missing_toml(*_, **__):
    raise Exception("pip install tomli tomli-w tomlkit")


@dataclass
class TomlModule:
    loads: Callable[[Any], Union[dict, list]] = raise_missing_toml
    dumps: Callable[[Any], str] = raise_missing_toml

    @property
    def loads_ready(self) -> bool:
        return self.loads != raise_missing_toml

    @property
    def dumps_ready(self) -> bool:
        return self.dumps != raise_missing_toml


toml = TomlModule()
_, version_minor, *__ = sys.version_info
with suppress(ModuleNotFoundError):
    import tomlkit

    def loads(value: str) -> Union[dict, list]:
        loaded = tomlkit.loads(value)
        return loaded.value

    toml.loads = loads
    toml.dumps = tomlkit.dumps

if not toml.loads_ready:
    try:
        import tomli

        toml.loads = tomli.loads
    except ModuleNotFoundError:
        if version_minor >= 11:
            import tomllib

            toml.loads = tomllib.loads
if not toml.loads_ready:
    logger.warning("no library for reading toml files: pip install tomlkit | tomli ")
if not toml.dumps_ready:
    try:
        import tomli_w

        toml.dumps = tomli_w.dumps
    except ModuleNotFoundError:
        logger.warning("tomlkit or tomli-w not installed, dumping toml will not work")


_dumps = toml.dumps


def dump_toml_str(data: object, **kwargs) -> str:
    return _dumps(data, **kwargs)


_loads = toml.loads


def parse_toml_str(data: str, **kwargs) -> Union[dict, list]:
    return _loads(data, **kwargs)


_array_pattern = re.compile(r"[^\s]+\s=\s\[(.*)\]$")


def add_line_breaks(updated: str) -> str:
    lines = []
    for line in updated.splitlines():
        if len(line) > 88 and (long_array_match := _array_pattern.match(line)):
            inner_content_old = long_array_match.group(1)
            inner_content_new = inner_content_old.replace(", ", ",\n")
            inner_content_new = indent(inner_content_new, "  ")
            inner_content_new = f"\n{inner_content_new},\n"
            line = line.replace(inner_content_old, inner_content_new)
        lines.append(line)
    return "\n".join(lines)
