import logging
import sys
from contextlib import suppress
from dataclasses import dataclass
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
