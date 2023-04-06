from dataclasses import dataclass, fields, is_dataclass
from typing import Any, Callable, Sequence, Type, Union


def field_names(cls: Union[Type, Any]):
    if is_dataclass(cls):
        return [f.name for f in fields(cls)]
    raise Exception(f"Cannot get fields from Non dataclass: {cls.__name__}")


def values(instance: dataclass):
    return [getattr(instance, name) for name in field_names(instance.__class__)]


def copy(instance: dataclass, exclude: Sequence[str] = None, update: dict = None):
    if exclude:

        def include(field_name: str):
            return field_name not in exclude

        kwargs = key_values(instance, filter=include)
    else:
        kwargs = key_values(instance)
    if update:
        kwargs.update(update)
    return type(instance)(**kwargs)


def key_values(instance: dataclass, filter: Callable[[str], bool] = None):
    return {
        field_name: getattr(instance, field_name)
        for field_name in field_names(instance)
        if filter is None or filter(field_name)
    }
