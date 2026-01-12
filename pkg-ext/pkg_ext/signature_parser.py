from __future__ import annotations

import dataclasses
import inspect
from contextlib import suppress
from typing import Any, Callable, ClassVar, get_origin, get_type_hints

from pkg_ext.models.api_dump import (
    CallableSignature,
    ClassFieldInfo,
    FuncParamInfo,
    ParamDefault,
    ParamKind,
)

_PARAM_KIND_MAP = {
    inspect.Parameter.POSITIONAL_ONLY: ParamKind.POSITIONAL_ONLY,
    inspect.Parameter.POSITIONAL_OR_KEYWORD: ParamKind.POSITIONAL_OR_KEYWORD,
    inspect.Parameter.VAR_POSITIONAL: ParamKind.VAR_POSITIONAL,
    inspect.Parameter.KEYWORD_ONLY: ParamKind.KEYWORD_ONLY,
    inspect.Parameter.VAR_KEYWORD: ParamKind.VAR_KEYWORD,
}


def _annotation_str(annotation: Any) -> str | None:
    if annotation is inspect.Parameter.empty:
        return None
    if isinstance(annotation, type):
        return annotation.__name__
    return str(annotation)


def parse_param_default(param: inspect.Parameter) -> ParamDefault | None:
    if param.default is inspect.Parameter.empty:
        return None
    with suppress(ImportError):
        from pydantic.fields import FieldInfo

        if isinstance(param.default, FieldInfo):
            if param.default.default_factory is not None:
                return ParamDefault(value_repr="...", is_factory=True)
            return ParamDefault(value_repr=repr(param.default.default))
    return ParamDefault(value_repr=repr(param.default))


def parse_func_param(param: inspect.Parameter) -> FuncParamInfo:
    return FuncParamInfo(
        name=param.name,
        kind=_PARAM_KIND_MAP[param.kind],
        type_annotation=_annotation_str(param.annotation),
        default=parse_param_default(param),
    )


def parse_signature(obj: Callable) -> CallableSignature:
    try:
        sig = inspect.signature(obj)
    except (ValueError, TypeError):
        return CallableSignature()
    params = [parse_func_param(p) for p in sig.parameters.values()]
    return CallableSignature(
        parameters=params,
        return_annotation=_annotation_str(sig.return_annotation),
    )


def parse_direct_bases(cls: type) -> list[str]:
    return [base.__name__ for base in cls.__bases__ if base is not object]


def _parse_field_default(field: Any) -> ParamDefault | None:
    from pydantic.fields import FieldInfo

    if isinstance(field, FieldInfo):
        if field.default_factory is not None:
            return ParamDefault(value_repr="...", is_factory=True)
        if field.default is not None:
            return ParamDefault(value_repr=repr(field.default))
    return None


def _extract_env_vars(cls: type, field_name: str) -> list[str] | None:
    try:
        from pydantic_settings import BaseSettings
        from pydantic_settings.sources import EnvSettingsSource

        if not issubclass(cls, BaseSettings):
            return None
        model_config = cls.model_config
        source = EnvSettingsSource(
            cls,
            case_sensitive=model_config.get("case_sensitive"),  # type: ignore
            env_prefix=model_config.get("env_prefix"),  # type: ignore
            env_nested_delimiter=model_config.get("env_nested_delimiter"),  # type: ignore
        )
        model_field = cls.model_fields[field_name]
        field_infos = source._extract_field_info(model_field, field_name)
        return [info[1] for info in field_infos]
    except (ImportError, Exception):
        return None


def _parse_pydantic_fields(cls: type) -> list[ClassFieldInfo]:
    fields: list[ClassFieldInfo] = []
    for name, field in cls.model_fields.items():  # type: ignore
        if name.startswith("_"):
            continue
        fields.append(
            ClassFieldInfo(
                name=name,
                type_annotation=str(field.annotation) if field.annotation else None,
                default=_parse_field_default(field),
                is_class_var=False,
                is_computed=False,
                description=field.description,
                deprecated=field.deprecated,
                env_vars=_extract_env_vars(cls, name),
            )
        )
    if hasattr(cls, "model_computed_fields"):
        for name, computed in cls.model_computed_fields.items():  # type: ignore
            if name.startswith("_"):
                continue
            fields.append(
                ClassFieldInfo(
                    name=name,
                    type_annotation=(
                        str(computed.return_type) if computed.return_type else None
                    ),
                    is_computed=True,
                    description=computed.description
                    if hasattr(computed, "description")
                    else None,
                )
            )
    return fields


def _parse_dataclass_fields(cls: type) -> list[ClassFieldInfo]:
    hints = get_type_hints(cls)
    fields: list[ClassFieldInfo] = []
    for f in dataclasses.fields(cls):
        if f.name.startswith("_"):
            continue
        annotation = hints.get(f.name)
        is_class_var = get_origin(annotation) is ClassVar
        default: ParamDefault | None = None
        if f.default is not dataclasses.MISSING:
            default = ParamDefault(value_repr=repr(f.default))
        elif f.default_factory is not dataclasses.MISSING:
            default = ParamDefault(value_repr="...", is_factory=True)
        fields.append(
            ClassFieldInfo(
                name=f.name,
                type_annotation=str(annotation) if annotation else None,
                default=default,
                is_class_var=is_class_var,
            )
        )
    return fields


def parse_class_fields(cls: type) -> list[ClassFieldInfo] | None:
    """Dispatch to Pydantic or dataclass field parser. Returns None for plain classes."""
    with suppress(ImportError):
        from pydantic import BaseModel

        if isinstance(cls, type) and issubclass(cls, BaseModel):
            return _parse_pydantic_fields(cls)
    if dataclasses.is_dataclass(cls):
        return _parse_dataclass_fields(cls)
    return None
