from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any, Callable, Optional, TypeVar

from model_lib.model_dump import dump as model_dump
from typing_extensions import TypeAlias

logger = logging.getLogger(__name__)
T = TypeVar("T")

dump_call: TypeAlias = Callable[[T], str]
dump_parse: TypeAlias = Optional[tuple[dump_call, dump_call, Callable[[str], Any]]]


def orjson_dumps_parse() -> dump_parse:
    with suppress(ModuleNotFoundError):
        import orjson

        def dump_orjson(instance: T) -> str:
            return orjson.dumps(
                instance, default=model_dump, option=orjson.OPT_NON_STR_KEYS
            ).decode("utf-8")

        def pretty_dump_orjson(instance: T) -> str:
            return orjson.dumps(
                instance,
                default=model_dump,
                option=orjson.OPT_NON_STR_KEYS
                | orjson.OPT_SORT_KEYS
                | orjson.OPT_INDENT_2,
            ).decode("utf-8")

        return dump_orjson, pretty_dump_orjson, orjson.loads
    logger.warning(
        "orjson not installed running with stdlib json (pip install orjson to install a faster json serializer)"
    )
    return None


def stdlib_dumps_parse() -> dump_parse:
    import json

    def dump_stdlib(instance: T) -> str:
        return json.dumps(instance, indent=None, separators=(",", ":"))

    def pretty_dump_stdlib(instance: T) -> str:
        return json.dumps(
            instance, indent=2, sort_keys=True, ensure_ascii=False, default=model_dump
        )

    return dump_stdlib, pretty_dump_stdlib, json.loads


for func in [orjson_dumps_parse, stdlib_dumps_parse]:
    if exist := func():
        dump, pretty_dump, parse = exist
        break
else:
    raise Exception("Should never happen, stdlib always available!")
