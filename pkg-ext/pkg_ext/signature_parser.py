from __future__ import annotations

import dataclasses
import inspect
import types
import typing
from contextlib import suppress
from typing import Any, Callable, ClassVar, Union, get_origin, get_type_hints

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
    """Convert annotation to string using simple names, not full module paths."""
    if annotation is inspect.Parameter.empty:
        return None
    if annotation is None or annotation is type(None):
        return "None"
    if isinstance(annotation, type):
        return annotation.__name__

    # Handle Union types (X | Y or Union[X, Y])
    origin = get_origin(annotation)
    # Python 3.10+ uses types.UnionType for X | Y syntax
    if isinstance(annotation, types.UnionType):
        args = typing.get_args(annotation)
        arg_strs = [_annotation_str(arg) for arg in args]
        return " | ".join(a for a in arg_strs if a)

    if origin is not None:
        args = typing.get_args(annotation)
        if origin is Union:
            # Union type - join args with |
            arg_strs = [_annotation_str(arg) for arg in args]
            return " | ".join(a for a in arg_strs if a)
        # Generic type like list[str], dict[str, int]
        origin_name = origin.__name__ if hasattr(origin, "__name__") else str(origin)
        if args:
            arg_strs = [_annotation_str(arg) for arg in args]
            return f"{origin_name}[{', '.join(a for a in arg_strs if a)}]"
        return origin_name

    return str(annotation)


def _normalize_module(module: str, pkg_name: str = "") -> str:
    """Normalize internal module paths by dropping trailing underscore-prefixed segments.

    Examples:
        - pathlib._local -> pathlib
        - collections._abc -> collections
        - mypackage._internal.utils -> mypackage (unless within mypackage itself)

    If pkg_name is provided, internal modules within that package are preserved.
    """
    parts = module.split(".")
    # Drop trailing parts that start with underscore (internal implementation details)
    while len(parts) > 1 and parts[-1].startswith("_"):
        # Keep internal modules if they're part of the current package
        if pkg_name and parts[0] == pkg_name:
            break
        parts.pop()
    return ".".join(parts)


def _annotation_import(annotation: Any, pkg_name: str = "") -> str | None:
    """Extract the full import path for a type annotation.

    Handles union types (X | Y) by returning imports for all component types.
    Returns None for builtins.
    """
    if annotation is inspect.Parameter.empty:
        return None

    # Handle Union types (X | Y or Union[X, Y])
    if isinstance(annotation, types.UnionType):
        # Return first non-builtin import from union components
        for arg in typing.get_args(annotation):
            if result := _annotation_import(arg, pkg_name):
                return result
        return None

    origin = get_origin(annotation)
    if origin is Union:
        for arg in typing.get_args(annotation):
            if result := _annotation_import(arg, pkg_name):
                return result
        return None

    if isinstance(annotation, type):
        module = annotation.__module__
        name = annotation.__name__
        if module == "builtins":
            return None
        module = _normalize_module(module, pkg_name)
        return f"{module}.{name}"
    return None


def _collect_all_annotation_imports(annotation: Any, pkg_name: str = "") -> list[str]:
    """Collect ALL import paths from a type annotation, including all union members."""
    imports: list[str] = []

    if annotation is inspect.Parameter.empty:
        return imports

    # Handle Union types - collect from all components
    if isinstance(annotation, types.UnionType):
        for arg in typing.get_args(annotation):
            imports.extend(_collect_all_annotation_imports(arg, pkg_name))
        return imports

    origin = get_origin(annotation)
    if origin is Union:
        for arg in typing.get_args(annotation):
            imports.extend(_collect_all_annotation_imports(arg, pkg_name))
        return imports

    # Handle generic types like list[SomeType]
    if origin is not None:
        for arg in typing.get_args(annotation):
            imports.extend(_collect_all_annotation_imports(arg, pkg_name))
        return imports

    if isinstance(annotation, type):
        module = annotation.__module__
        name = annotation.__name__
        if module != "builtins":
            module = _normalize_module(module, pkg_name)
            imports.append(f"{module}.{name}")

    return imports


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


def _parse_func_param(
    param: inspect.Parameter, resolved_annotation: Any | None = None
) -> FuncParamInfo:
    annotation = (
        resolved_annotation if resolved_annotation is not None else param.annotation
    )
    return FuncParamInfo(
        name=param.name,
        kind=_PARAM_KIND_MAP[param.kind],
        type_annotation=_annotation_str(annotation),
        type_imports=_collect_all_annotation_imports(annotation),
        default=parse_param_default(param),
    )


def parse_signature(obj: Callable) -> CallableSignature:
    try:
        sig = inspect.signature(obj)
    except (ValueError, TypeError):
        return CallableSignature()

    # Resolve string annotations to actual types
    try:
        hints = get_type_hints(obj)
    except Exception:
        hints = {}

    params = [_parse_func_param(p, hints.get(p.name)) for p in sig.parameters.values()]
    return_hint = hints.get("return")
    return CallableSignature(
        parameters=params,
        return_annotation=_annotation_str(return_hint) if return_hint else None,
        return_type_imports=_collect_all_annotation_imports(return_hint)
        if return_hint
        else [],
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
                type_annotation=_annotation_str(field.annotation),
                type_imports=_collect_all_annotation_imports(field.annotation),
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
                    type_annotation=_annotation_str(computed.return_type),
                    type_imports=_collect_all_annotation_imports(computed.return_type),
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
                type_annotation=_annotation_str(annotation),
                type_imports=_collect_all_annotation_imports(annotation),
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
