from dataclasses import asdict, dataclass

import pytest
from model_lib.serialize import dump

from model_lib import Entity, Event, register_dumper


@dataclass
class _MyClass:
    name: str
    age: int


register_dumper(_MyClass, asdict, allow_override=True)


class _MyEntity(Entity):
    name: str
    age: int


class _MyEvent(Event):
    name: str
    age: int


@pytest.mark.parametrize("cls", [_MyClass, _MyEntity, _MyEvent])
def test_safe_dump(cls):
    dumped = dump(cls(name="espen", age=99), "yaml")
    assert dumped == "name: espen\nage: 99\n"
