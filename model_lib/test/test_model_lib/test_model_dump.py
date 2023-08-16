from functools import cached_property

import pytest
from model_lib.errors import DumperExist, NoDumper
from model_lib.model_base import Event
from model_lib.model_dump import dump, register_dumper
from zero_3rdparty.enum_utils import StrEnum

from model_lib import dump as dump_with_extension, FileFormat


def test_register_and_remove_call():
    def dump_str1(s: str):
        return "s1"

    def dump_str2(s: str):
        return s

    r1 = register_dumper(str, dump_str1)

    assert dump("123") == "s1"
    with pytest.raises(DumperExist):
        register_dumper(str, dump_str2, allow_override=False)
    r1()
    with pytest.raises(NoDumper) as exc:
        dump("123")
    assert exc.value.instance_type is str

    r2 = register_dumper(str, dump_str2, allow_override=True)
    assert dump("123") == "123"
    r2()
    with pytest.raises(NoDumper):
        dump("123")


class _Event(Event):
    name: str


def test_dumping_model():
    model = _Event(name="espen")
    assert dump(model) == {"name": model.name}


class _EventWithCachedProperty(Event):
    first_name: str
    last_name: str

    @cached_property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


def test_dumping_model_with_cached_property():
    model = _EventWithCachedProperty(first_name="first", last_name="second")
    assert model.full_name == "first second"
    assert dump(model) == {
        "first_name": "first",
        "last_name": "second",
    }


class _MyEnum(StrEnum):
    A = "A"
    B = "B"


def test_dumping_enum_to_yaml():
    assert dump_with_extension(dict(key=_MyEnum.A), "yaml") == "key: A\n"


def test_pydantic_json_dump():
    model = _EventWithCachedProperty(first_name="first", last_name="pydantic")
    assert model.full_name == "first pydantic"
    expected = '{"first_name":"first","last_name":"pydantic"}'
    assert dump_with_extension(model, "json_pydantic") == expected
    assert dump_with_extension(model, FileFormat.pydantic_json) == expected
