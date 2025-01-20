from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Type, TypeVar, Union

from pydantic import AfterValidator, BaseModel, TypeAdapter, conint
from pydantic.v1.datetime_parse import parse_datetime
from pydantic_settings import BaseSettings
from typing_extensions import Annotated, TypeAlias
from zero_3rdparty.datetime_utils import as_ms_precision_utc, ensure_tz


def env_var_name(
    settings: Union[BaseSettings, Type[BaseSettings]], field_name: str
) -> str:
    model_field = model_fields(settings).get(field_name)
    assert model_field, f"{settings}.{field_name} NOT FOUND"
    from pydantic_settings.sources import EnvSettingsSource

    model_config = settings.model_config
    source = EnvSettingsSource(
        settings,  # type: ignore
        case_sensitive=model_config.get("case_sensitive"),
        env_prefix=model_config.get("env_prefix"),
        env_nested_delimiter=model_config.get("env_nested_delimiter"),
    )
    field_infos = source._extract_field_info(model_field, field_name)
    return field_infos[0][1]


def env_var_names(settings: BaseSettings | Type[BaseSettings]) -> list[str]:
    return [env_var_name(settings, field_name) for field_name in field_names(settings)]


def parse_object_as(object_type: Type, data: Any):
    return TypeAdapter(object_type).validate_python(data)


def get_field_type(field):
    return field.annotation


def model_fields(model):
    return model.model_fields


def model_dump(model, **kwargs):
    return model.model_dump(**kwargs)


def model_json(model: BaseModel, **kwargs) -> str:
    return model.model_dump_json(**kwargs)


uint16 = conint(gt=-1, lt=65536)


def cls_defaults(model: Type[BaseModel]) -> dict:
    from pydantic_core import PydanticUndefined

    return {
        name: field.get_default()
        for name, field in model_fields(model).items()
        if field.get_default() != PydanticUndefined
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
    return model.model_copy(update=updates, deep=True)


parse_dt = parse_datetime


def ensure_timezone(value: datetime):
    if not value.tzinfo:
        return value.replace(tzinfo=timezone.utc)
    return value


utc_datetime: TypeAlias = Annotated[datetime, AfterValidator(ensure_timezone)]

utc_datetime_ms: TypeAlias = Annotated[datetime, AfterValidator(as_ms_precision_utc)]

StrBytesIntFloat: TypeAlias = Union[str, bytes, int, float]


def parse_dt_utc(value: Union[datetime, StrBytesIntFloat]):
    parsed = parse_dt(value)
    return ensure_tz(parsed)


def field_names(model_type: Type[BaseModel] | BaseModel) -> List[str]:
    return list(model_fields(model_type))
