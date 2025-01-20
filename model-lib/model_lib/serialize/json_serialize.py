from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional, TypeVar

import pydantic
from typing_extensions import TypeAlias

from model_lib.model_dump import dump as model_dump

logger = logging.getLogger(__name__)
T = TypeVar("T")

dump_call: TypeAlias = Callable[[T], str]
dump_parse: TypeAlias = Optional[tuple[dump_call, dump_call, Callable[[str], Any]]]

def dump(instance: Any) -> str:
    if isinstance(instance, pydantic.BaseModel):
        return instance.model_dump_json()
    return json.dumps(
        instance, indent=None, separators=(",", ":"), default=model_dump
    )

def pretty_dump(instance: Any) -> str:
    if isinstance(instance, pydantic.BaseModel):
        instance = instance.model_dump()  # type: ignore # pydantic doesn't support sort_keys by default
    return json.dumps(
        instance,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        default=model_dump,
    )

parse = json.loads