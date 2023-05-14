from __future__ import annotations

from dataclasses import fields
from typing import Callable, Type, TypeVar, Container

T = TypeVar('T')


def field_names(cls: Type[T] | T):
    return [f.name for f in fields(cls)]  # type: ignore


def values(instance: T):
    return [getattr(instance, name) for name in field_names(instance)]


def copy(instance: T, exclude: Container[str] | None = None, update: dict| None = None):
    if exclude:

        def include(field_name: str):
            return field_name not in exclude # type: ignore

        kwargs = key_values(instance, filter=include)
    else:
        kwargs = key_values(instance)
    if update:
        kwargs.update(update)
    return type(instance)(**kwargs)


def key_values(instance: T, filter: Callable[[str], bool] | None = None):
    return {
        field_name: getattr(instance, field_name)
        for field_name in field_names(instance)
        if filter is None or filter(field_name)
    }
