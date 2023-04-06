from __future__ import annotations

from asyncio import CancelledError as AsyncCancelledError
from collections import ChainMap, Counter, defaultdict, deque
from contextlib import suppress
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from functools import singledispatch
from pathlib import Path
from typing import Callable, Literal, Type, TypeAlias, TypeVar, ValuesView
from uuid import UUID

from model_lib.errors import DumperExist, NoDumper

T = TypeVar("T")
PrimitiveT: TypeAlias = dict | str | list | int | float | bool
DumpCall: TypeAlias = Callable[[T], PrimitiveT]
UnregisterCall: TypeAlias = Callable[[], None]


def registered_types() -> ValuesView[Type]:
    return _registered_dumpers.values()


def add_unregister(func: T) -> T:
    """https://stackoverflow.com/questions/25951651/unregister-for-
    singledispatch."""
    # build a dictionary mapping names to closure cells
    closure = dict(zip(func.register.__code__.co_freevars, func.register.__closure__))
    registry = closure["registry"].cell_contents
    dispatch_cache = closure["dispatch_cache"].cell_contents

    def unregister(cls):
        del registry[cls]
        dispatch_cache.clear()

    func.unregister = unregister
    return func


@add_unregister
@singledispatch
def dump(instance: object) -> PrimitiveT:
    raise NoDumper(type(instance))


_registered_dumpers: dict[str, Type] = {}


def _register_yaml_dumper(instance_type: Type[T], dump_call: DumpCall):
    if instance_type in (str, bytes, bool, int, float):
        return
    with suppress(ModuleNotFoundError):
        import yaml

        def represent(dumper: yaml.BaseDumper, instance: T):
            data = dump_call(instance)
            return dumper.represent_data(data)

        yaml.add_representer(instance_type, represent, yaml.SafeDumper)
        yaml.add_representer(instance_type, represent, yaml.Dumper)


def register_dumper(
    instance_type: Type[T],
    dump_call: DumpCall,
    allow_override: bool | Literal["never"] = False,
) -> UnregisterCall:
    type_name = instance_type.__name__
    allow_override = allow_override or type_name.startswith("_")
    found_existing = type_name in _registered_dumpers
    if found_existing and (allow_override in (False, "never")):
        raise DumperExist(instance_type, instance_type)
    _registered_dumpers[type_name] = instance_type
    dump.register(instance_type)(dump_call)

    def unregister():
        return dump.unregister(instance_type)

    _register_yaml_dumper(instance_type, dump_call)

    return unregister


register_dumper(Counter, dict)
register_dumper(defaultdict, dict)
register_dumper(ChainMap, dict)


register_dumper(deque, list)
register_dumper(set, list)

register_dumper(Decimal, str)
register_dumper(UUID, str)
register_dumper(bytes, str)
register_dumper(Path, str)

register_dumper(datetime, datetime.isoformat)
register_dumper(date, date.isoformat)
register_dumper(Enum, lambda e: e.value)

register_dumper(type, lambda t: t.__name__)
register_dumper(Exception, repr)
register_dumper(AsyncCancelledError, repr)
