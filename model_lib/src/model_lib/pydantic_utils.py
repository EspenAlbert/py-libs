from datetime import datetime, timedelta, timezone
from functools import singledispatch
from typing import List, Type, TypeVar, Union

from pydantic import BaseModel, conint
from pydantic.datetime_parse import StrBytesIntFloat, parse_datetime
from zero_lib.datetime_utils import as_ms_precision_utc, ensure_tz

from model_lib import register_dumper

uint16 = conint(gt=-1, lt=65536)


def cls_defaults(model: Type[BaseModel]) -> dict:
    return {
        name: field.get_default()
        for name, field in model.__fields__.items()
        if field.get_default() is not None
    }


def cls_defaults_required_as(
    model: Type[BaseModel], required_value: str = "CHANGE_ME"
) -> dict:
    defaults = cls_defaults(model)
    return {key: defaults.get(key, required_value) for key in model.__fields__}


def cls_local_defaults_required_as(
    model: Type[BaseModel], required_value: str = "CHANGE_ME"
) -> dict:
    local_hints = model.__annotations__
    defaults = cls_defaults(model)
    return {
        key: defaults.get(key, required_value)
        for key in model.__fields__
        if key in local_hints
    }


T = TypeVar("T")


def has_path(model: Type[BaseModel], path: str) -> bool:
    current_model = model
    for sub_path in path.split("."):
        if model_field := current_model.__fields__.get(sub_path):
            current_model = model_field.type_
        else:
            return False
    return True


BaseModelT = TypeVar("BaseModelT", bound=BaseModel)


def copy_and_validate(model: BaseModelT, **updates) -> BaseModelT:
    cls = type(model)
    new_model = model.copy(update=updates, deep=True)
    return cls(**new_model.dict())


parse_dt = parse_datetime


class _utc_datetime(datetime):
    @classmethod
    def __get_validators__(cls):
        yield parse_datetime
        yield cls.ensure_utc

    @classmethod
    def ensure_utc(cls, value: datetime):
        if not value.tzinfo:
            return value.replace(tzinfo=timezone.utc)
        return value


class _utc_datetime_ms(datetime):
    @classmethod
    def __get_validators__(cls):
        yield parse_datetime
        yield as_ms_precision_utc


# necessary otherwise pycharm complains when passing a datetime and not utc_datetime
utc_datetime = Union[_utc_datetime, datetime]
#: handy for mongo which only supports ms anyway.
#: WARNING: do not use with default_factory
utc_datetime_ms = Union[_utc_datetime_ms, datetime]


def parse_dt_utc(value: Union[datetime, StrBytesIntFloat]):
    parsed = parse_dt(value)
    return ensure_tz(parsed)


def field_names(model_type: Type[BaseModel] | BaseModel) -> List[str]:
    return list(model_type.__fields__)


@singledispatch
def parse_timedelta(td: timedelta):
    return td


@parse_timedelta.register
def parse_timedelta(td: float):
    return timedelta(seconds=td)


class _timedelta(timedelta):
    @classmethod
    def __get_validators__(cls):
        yield parse_timedelta


timedelta_dumpable = Union[_timedelta, timedelta]


def as_total_seconds(td: timedelta):
    return td.total_seconds()


register_dumper(timedelta, as_total_seconds)
