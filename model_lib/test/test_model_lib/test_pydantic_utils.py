from datetime import timedelta, timezone

import pydantic
from pydantic import BaseModel, Field

from model_lib import Event
from model_lib.constants import FileFormat
from model_lib.pydantic_utils import (
    IS_PYDANTIC_V2,
    BaseSettings,
    cls_defaults,
    cls_defaults_required_as,
    cls_local_defaults_required_as,
    copy_and_validate,
    env_var_name,
    env_var_names,
    has_path,
    parse_dt,
    parse_object_as,
    timedelta_dumpable,
    utc_datetime,
    utc_datetime_ms,
)
from model_lib.serialize import dump, parse_model
from zero_3rdparty.iter_utils import ignore_falsy


class _ExampleModel(BaseModel):
    name: str


def test_parse_object_as():
    found = parse_object_as(_ExampleModel, {"name": "test"})
    assert found == _ExampleModel(name="test")


def test_timedelta_dumpable():
    class _MyModelTimedelta(Event):
        td: timedelta_dumpable

    model = _MyModelTimedelta(td=timedelta(hours=1, weeks=1))
    dumped = dump(model, FileFormat.yaml)
    model2 = parse_model(dumped, format=FileFormat.yaml, t=_MyModelTimedelta)
    assert model == model2


if IS_PYDANTIC_V2:
    from pydantic import model_serializer

    class _ExampleDumpModel(BaseModel):
        name: str
        items: list[str] = Field(default_factory=list)

        @model_serializer(mode="wrap")
        def ignore_falsy(
            self,
            nxt: pydantic.SerializerFunctionWrapHandler,
            _: pydantic.FieldSerializationInfo,
        ):
            serialized = nxt(self)
            return ignore_falsy(**serialized)

    def test_model_serializer():
        model = _ExampleDumpModel(name="no_items")
        assert model.model_dump() == {"name": "no_items"}


class MySettings(BaseSettings):
    if IS_PYDANTIC_V2:
        model_config = dict(env_prefix="my_", case_sensitive=True)
    else:

        class Config:
            env_prefix = "my_"
            case_sensitive = False

    var1: str
    if IS_PYDANTIC_V2:
        var_specific: str = Field(validation_alias="OTHER_NAME")
    else:
        var_specific: str = Field(env="OTHER_NAME")


def test_env_var_name():
    assert env_var_name(MySettings, "var1") == "my_var1"
    assert env_var_name(MySettings, "var_specific") == "OTHER_NAME"
    assert env_var_names(MySettings) == ["my_var1", "OTHER_NAME"]


class _MyModel(Event):
    name: str
    age: int
    default: str = "my-default"


def test_copy_and_validate():
    model1 = _MyModel(name="m1", age=10)
    model2 = copy_and_validate(model1, name="m2")
    assert model1.age == model2.age
    assert model1.name != model2.name


def test_cls_defaults():
    assert cls_defaults(_MyModel) == {"default": "my-default"}


def test_cls_defaults_required_as():
    assert cls_defaults_required_as(_MyModel) == {
        "age": "CHANGE_ME",
        "default": "my-default",
        "name": "CHANGE_ME",
    }


class _MySubModel(_MyModel):
    one_required: str
    another_default: str = "default2"


def test_cls_local_defaults_required_as():
    assert cls_local_defaults_required_as(_MySubModel) == {
        "another_default": "default2",
        "one_required": "CHANGE_ME",
    }


class _MyChild(Event):
    name: str


class _MyParent(Event):
    child: _MyChild


def test_has_path():
    child = _MyChild(name="child")
    parent = _MyParent(child=child)
    assert has_path(child, "name")
    assert not has_path(child, "age")
    assert has_path(parent, "child.name")
    assert not has_path(parent, "child.age")


class _TimeModel(Event):
    utc: utc_datetime
    utc_ms: utc_datetime_ms
    timedelta: timedelta_dumpable = 0


def test_utc_datetime():
    dt_no_timezone = parse_dt("2023-08-16T16:42:14")
    assert dt_no_timezone.tzinfo is None
    model = _TimeModel(utc=dt_no_timezone, utc_ms=dt_no_timezone)
    assert model.utc.tzinfo == timezone.utc


def test_utc_datetime_ms():
    dt_no_timezone = parse_dt("2023-08-16T16:42:14.123456")
    assert dt_no_timezone.microsecond % 1000 != 0
    model = _TimeModel(utc=dt_no_timezone, utc_ms=dt_no_timezone)
    assert model.utc_ms.microsecond % 1000 == 0


def test_dumping_time_model():
    dt = parse_dt("2023-08-16T16:42:14.123456")
    model = _TimeModel(utc=dt, utc_ms=dt, timedelta=30)
    assert model.timedelta == timedelta(seconds=30)
    expected_json = '{"utc":"2023-08-16T16:42:14.123456+00:00","utc_ms":"2023-08-16T16:42:14.123000+00:00","timedelta":30.0}'
    assert dump(model, "json") == expected_json
    assert parse_model(expected_json, _TimeModel) == model
