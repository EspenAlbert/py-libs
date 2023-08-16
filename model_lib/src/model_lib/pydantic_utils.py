from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import singledispatch
from typing import Any, List, Type, TypeVar, Union

import pydantic
from pydantic import BaseModel, conint
from typing_extensions import TypeAlias

IS_PYDANTIC_V2 = int(pydantic.VERSION.split(".")[0]) >= 2
use_pydantic_settings = False
try:
    from pydantic_settings import BaseSettings

except ModuleNotFoundError:
    if IS_PYDANTIC_V2:
        from pydantic.v1.env_settings import BaseSettings
    else:
        from pydantic import BaseSettings
if IS_PYDANTIC_V2:
    from pydantic import TypeAdapter
    from pydantic.v1.datetime_parse import parse_datetime
else:
    from pydantic.datetime_parse import parse_datetime
    from pydantic import parse_obj_as

from model_lib.model_dump import register_dumper
from zero_3rdparty.datetime_utils import as_ms_precision_utc, ensure_tz
from zero_3rdparty.iter_utils import first


def decode_settings_error(error: Exception) -> str:
    """
    >>> decode_settings_error(Exception('error parsing JSON for "my_env_list_name"'))
    'my_env_list_name'
    """
    message: str = error.args[0]
    error_text, error_field, empty = message.split('"')
    return error_field


def env_var_name(
    settings: Union[BaseSettings, Type[BaseSettings]], field_name: str
) -> str:
    model_field = get_model_fields(settings).get(field_name)
    assert model_field, f"{settings}.{field_name} NOT FOUND"
    extra_info = model_field.field_info.extra
    if env := extra_info.get("env"):
        return env
    return first(extra_info["env_names"], str)


def env_var_names(settings: BaseSettings | Type[BaseSettings]) -> list[str]:
    return [env_var_name(settings, field_name) for field_name in field_names(settings)]


def parse_object_as(object_type: Type, data: Any):
    if IS_PYDANTIC_V2:
        return TypeAdapter(object_type).validate_python(data)
    else:
        return parse_obj_as(object_type, data)


def get_field_type(field):
    if IS_PYDANTIC_V2:
        return field.annotation
    else:
        return field.type_


def get_model_fields(model):
    if IS_PYDANTIC_V2:
        return model.model_fields
    else:
        return model.__fields__


def parse_model(model_type: Type[BaseModel], data: Any):
    if IS_PYDANTIC_V2:
        return model_type.model_validate(data)
    else:
        return model_type.parse_obj(data)


def get_extra_field_info(field, parameter: str):
    if IS_PYDANTIC_V2:
        if field.json_schema_extra is not None:
            return field.json_schema_extra.get(parameter)
        return None
    else:
        return field.field_info.extra.get(parameter)


def get_config_value(model, parameter: str):
    if IS_PYDANTIC_V2:
        return model.model_config.get(parameter)
    else:
        return getattr(model.Config, parameter, None)


def model_dump(model, **kwargs):
    if IS_PYDANTIC_V2:
        return model.model_dump(**kwargs)
    else:
        return model.dict(**kwargs)


def model_json(model: BaseModel, **kwargs):
    if IS_PYDANTIC_V2:
        return model.model_dump_json(**kwargs)
    else:
        return model.json(**kwargs)


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
StrBytesIntFloat: TypeAlias = Union[str, bytes, int, float]


def parse_dt_utc(value: Union[datetime, StrBytesIntFloat]):
    parsed = parse_dt(value)
    return ensure_tz(parsed)


def field_names(model_type: Type[BaseModel] | BaseModel) -> List[str]:
    return list(get_model_fields(model_type))


@singledispatch
def parse_timedelta(td: Union[timedelta, float]):
    raise NotImplementedError


@parse_timedelta.register
def _parse_timedelta_td(td: timedelta):
    return td


@parse_timedelta.register
def _parse_timedelta_float(td: float):
    return timedelta(seconds=td)


class _timedelta(timedelta):
    @classmethod
    def __get_validators__(cls):
        yield parse_timedelta


timedelta_dumpable = Union[_timedelta, timedelta]


def as_total_seconds(td: timedelta):
    return td.total_seconds()


register_dumper(timedelta, as_total_seconds)
