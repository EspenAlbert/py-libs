"""Heavily inspired by https://github.com/ivan-korobkov/python-inject But
choosing to simplify by providing a smaller set of methods."""
from __future__ import annotations

import logging
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Callable, Generic, Type, TypeVar, Union, cast

from typing_extensions import TypeAlias
from zero_3rdparty.error import BaseError
from zero_3rdparty.iter_utils import first_or_none, public_dict
from zero_3rdparty.object_name import as_name

logger = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass
class Provider(Generic[T]):
    provider: Callable[[], T]


ProviderOrInstance: TypeAlias = Union[T, Provider[T]]
_dependencies: dict[Type, ProviderOrInstance] = {}
_infer_instances: list[Any] = []


class DependencyNotSet(BaseError):
    def __init__(self, cls: Type):
        self.cls = cls


def instance(cls: Type[T]) -> T:
    if _instance := _dependencies.get(cls):
        return _instance.provider() if isinstance(_instance, Provider) else _instance
    raise DependencyNotSet(cls)


def instance_or_inferred(cls: Type[T]) -> T:
    try:
        return instance(cls)
    except DependencyNotSet as e:
        inferable = _infer_instances + list(_dependencies.values())
        if found := first_or_none(inferable, cls):
            _dependencies[cls] = found
            return found
        raise e


def instance_or_none(cls: Type[T]) -> T | None:
    with suppress(DependencyNotSet):
        return instance(cls)
    return None


class ReBindingError(BaseError):
    def __init__(self, classes: list[Type]):
        self.classes = classes


def get_dependencies() -> dict[Type, Provider[T] | T]:
    return _dependencies


def bind_infer_instances(instances: list[Any], clear_first: bool = False):
    global _infer_instances
    if clear_first:
        _infer_instances.clear()
    _infer_instances.extend(instances)


def bind_instances(
    instances: dict[Type[T], Provider | T],
    clear_first: bool = False,
    allow_re_binding: bool = False,
):
    if clear_first:
        _dependencies.clear()
    if not allow_re_binding:
        if re_bindings := [cls for cls in instances if cls in _dependencies]:
            raise ReBindingError(re_bindings)
    _dependencies.update(instances)


@dataclass
class _InjectDescriptor(Generic[T]):
    cls: Type[T]

    def __get__(self, _instance, owner) -> T | _InjectDescriptor[T]:
        with suppress(DependencyNotSet):
            return instance(self.cls)
        if _instance is not None:
            raise AttributeError
        return self


def as_dependency_cls(maybe_dependency: Any):
    if isinstance(maybe_dependency, _InjectDescriptor):
        return maybe_dependency.cls


def dependency(cls: Type[T]) -> T:
    return cast(T, _InjectDescriptor(cls))


class MissingDependencies(BaseError):
    def __init__(self, missing_dependencies: dict[Type, list[str]]):
        self.missing_dependencies = missing_dependencies


def _as_member_dependencies(member: Any) -> list[tuple[str, Type[T]]]:
    """
    Tip:
        cannot use inspect.getmembers since it will ignore dependencies
        due to AttributeError raised in resolve_dependency
    """
    member_type = type(member)
    return [
        (name, cls)
        for name, dependency_property in public_dict(
            member_type, recursive=True
        ).items()
        if (cls := as_dependency_cls(dependency_property))
    ]


def validate_dependencies(instances: list[Any], allow_binding: bool = True) -> None:
    """Raises MissingDependencies."""
    missing_dependencies: dict[Type, list[str]] = defaultdict(list)
    for each_instance in instances:
        for prop_name, cls in _as_member_dependencies(each_instance):  # type: ignore
            if cls not in _dependencies:
                if allow_binding and (
                    inferred_instance := first_or_none(instances, cls)
                ):
                    logger.info(f"binding by inferring {cls} to {inferred_instance}")
                    bind_instances({cls: inferred_instance})
                else:
                    prop_path = f"{as_name(each_instance)}.{prop_name}"
                    missing_dependencies[cls].append(prop_path)
    if missing_dependencies:
        raise MissingDependencies(missing_dependencies)
