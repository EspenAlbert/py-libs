from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import singledispatch
from typing import Any, List, Type, TypeVar, Union

import pydantic
from pydantic import BaseModel, conint
from typing_extensions import Annotated, TypeAlias

IS_SETTINGS_INSTALLED = False
IS_PYDANTIC_V2 = int(pydantic.VERSION.split(".")[0]) >= 2
use_pydantic_settings = False
try:
    from pydantic_settings import BaseSettings

    IS_SETTINGS_INSTALLED = True

except ModuleNotFoundError:
    if IS_PYDANTIC_V2:
        from pydantic.v1.env_settings import BaseSettings
    else:
        from pydantic import BaseSettings
if IS_PYDANTIC_V2:
    from pydantic import TypeAdapter
    from pydantic.v1.datetime_parse import parse_datetime
else:
    from pydantic import parse_obj_as
    from pydantic.datetime_parse import parse_datetime

from model_lib.model_dump import register_dumper  # noqa: E402
from zero_3rdparty.datetime_utils import as_ms_precision_utc, ensure_tz  # noqa: E402
from zero_3rdparty.iter_utils import first  # noqa: E402


def env_var_name(
    settings: Union[BaseSettings, Type[BaseSettings]], field_name: str
) -> str:
    model_field = model_fields(settings).get(field_name)
    assert model_field, f"{settings}.{field_name} NOT FOUND"
    if IS_SETTINGS_INSTALLED:
        from pydantic_settings.sources import EnvSettingsSource

        model_config = settings.model_config
        source = EnvSettingsSource(
            settings,  # type: ignore
            case_sensitive=model_config["case_sensitive"],
            env_prefix=model_config["env_prefix"],
            env_nested_delimiter=model_config["env_nested_delimiter"],
        )
        field_infos = source._extract_field_info(model_field, field_name)
        return field_infos[0][1]
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


def model_fields(model):
    if IS_PYDANTIC_V2:
        return model.model_fields
    else:
        return model.__fields__


def model_dump(model, **kwargs):
    if IS_PYDANTIC_V2:
        return model.model_dump(**kwargs)
    else:
        return model.dict(**kwargs)


def model_json(model: BaseModel, **kwargs) -> str:
    if IS_PYDANTIC_V2:
        return model.model_dump_json(**kwargs)
    else:
        return model.json(**kwargs)


uint16 = conint(gt=-1, lt=65536)


def cls_defaults(model: Type[BaseModel]) -> dict:
    if IS_PYDANTIC_V2:
        from pydantic_core import PydanticUndefined

        return {
            name: field.get_default()
            for name, field in model_fields(model).items()
            if field.get_default() != PydanticUndefined
        }
    return {
        name: field.get_default()
        for name, field in model_fields(model).items()
        if field.get_default() is not None
    }


def cls_defaults_required_as(
    model: Type[BaseModel], required_value: str = "CHANGE_ME"
) -> dict:
    defaults = cls_defaults(model)
    return {key: defaults.get(key, required_value) for key in model_fields(model)}


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


def has_path(model: Type[BaseModel] | BaseModel, path: str) -> bool:
    current_model = model
    for sub_path in path.split("."):
        if model_field := model_fields(current_model).get(sub_path):
            current_model = get_field_type(model_field)
        else:
            return False
    return True


BaseModelT = TypeVar("BaseModelT", bound=BaseModel)


def copy_and_validate(model: BaseModelT, **updates) -> BaseModelT:
    cls = type(model)
    if IS_PYDANTIC_V2:
        return model.model_copy(update=updates, deep=True)
    new_model = model.copy(update=updates, deep=True)
    return cls(**new_model.dict())


parse_dt = parse_datetime
if IS_PYDANTIC_V2:
    from pydantic import AfterValidator

    def ensure_timezone(value: datetime):
        if not value.tzinfo:
            return value.replace(tzinfo=timezone.utc)
        return value

    utc_datetime = Annotated[datetime, AfterValidator(ensure_timezone)]
else:

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

    utc_datetime = Union[_utc_datetime, datetime]

if IS_PYDANTIC_V2:
    utc_datetime_ms: TypeAlias = Annotated[
        datetime, AfterValidator(as_ms_precision_utc)
    ]
else:

    class _utc_datetime_ms(datetime):
        @classmethod
        def __get_validators__(cls):
            yield parse_datetime
            yield as_ms_precision_utc

    # necessary otherwise pycharm complains when passing a datetime and not utc_datetime
    #: handy for mongo which only supports ms anyway.
    #: WARNING: do not use with default_factory
    utc_datetime_ms: TypeAlias = Union[_utc_datetime_ms, datetime]
StrBytesIntFloat: TypeAlias = Union[str, bytes, int, float]


def parse_dt_utc(value: Union[datetime, StrBytesIntFloat]):
    parsed = parse_dt(value)
    return ensure_tz(parsed)


def field_names(model_type: Type[BaseModel] | BaseModel) -> List[str]:
    return list(model_fields(model_type))


@singledispatch
def parse_timedelta(td: object):
    raise NotImplementedError


@parse_timedelta.register
def _parse_timedelta_td(td: timedelta):
    return td


@parse_timedelta.register
def _parse_timedelta_float(td: float):
    return timedelta(seconds=td)


@parse_timedelta.register
def _parse_timedelta_int(td: int):
    return timedelta(seconds=td)


class _timedelta(timedelta):
    if IS_PYDANTIC_V2:

        @classmethod
        def __get_validators__(cls):
            yield cls.parse_timedelta

    else:

        @classmethod
        def __get_validators__(cls):
            yield parse_timedelta

    @classmethod
    def parse_timedelta(cls, value: Any, *_):
        return parse_timedelta(value)


timedelta_dumpable = Union[_timedelta, timedelta]


def as_total_seconds(td: timedelta):
    return td.total_seconds()


register_dumper(timedelta, as_total_seconds)
