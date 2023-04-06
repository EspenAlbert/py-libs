"""A dictionary with values specific to a thread/task Useful for:

- current Request in a http handler
- metadata during event processing
- storing unhandled errors
"""
from __future__ import annotations

from asyncio import Task, create_task
from collections import UserDict
from contextlib import suppress
from contextvars import Context, ContextVar
from dataclasses import dataclass
from typing import Callable, Coroutine, Protocol, TypeVar

from zero_lib.object_name import as_name

T = TypeVar("T")
KeyT = TypeVar("KeyT")


def identity(value: T) -> T:
    return value


class ParentChildCopy(Protocol):
    def __call__(
        self,
        parent: LocalDict,
        child: LocalDict,
        is_new_thread: bool,
        func_name: str,
    ) -> None:
        ...


@dataclass
class CopyConfig:
    """
    >>> c1 = CopyConfig()
    >>> c1.copy_to_thread
    False
    >>> c1.copy_to_task
    True
    """

    never: bool = False
    thread_copy: bool | Callable[[], bool] = False
    task_copy: bool | Callable[[], bool] = True
    copy_func: Callable[[T], T] = identity
    # is thread
    on_copy_done: ParentChildCopy | None = None

    @property
    def copy_to_thread(self) -> bool:
        if self.never:
            return False
        thread_copy = self.thread_copy
        if isinstance(thread_copy, bool):
            return thread_copy
        return thread_copy()

    @property
    def copy_to_task(self) -> bool:
        if self.never:
            return False
        task_copy = self.task_copy
        if isinstance(task_copy, bool):
            return task_copy
        return task_copy()


_copy_config: dict[type, CopyConfig] = {}
DEFAULT_CONFIG = CopyConfig()
assert not DEFAULT_CONFIG.copy_to_thread
assert DEFAULT_CONFIG.copy_to_task


def copy_value(key: KeyT, value: T) -> T:
    config = get_copy_behavior(key) or DEFAULT_CONFIG
    return config.copy_func(value)


def set_copy_behavior(t: KeyT, config: CopyConfig) -> None:
    global _copy_config
    _copy_config[t] = config


def get_copy_behavior(t: KeyT) -> CopyConfig | None:
    return _copy_config.get(t)


class LocalDict(UserDict):
    def set_instance(self, instance: T) -> T | None:
        """Returns the previous instance if set."""
        instance_type = type(instance)
        old = self.get(instance_type, None)
        self[instance_type] = instance
        return old

    def get_instance(self, instance_type: type[T]) -> T:
        return self[instance_type]

    def get_instance_or_none(self, instance_type: type[T]) -> T | None:
        return self.get(instance_type)

    def pop_instance(self, instance_type: type[T]) -> T | None:
        return self.pop(instance_type, None)

    def copy_to_new_thread(self, thread_name: str) -> LocalDict:
        on_done_calls = []

        def should_include(t: KeyT) -> bool:
            config = get_copy_behavior(t) or DEFAULT_CONFIG
            if on_done := config.on_copy_done:
                on_done_calls.append(on_done)
            return config.copy_to_thread

        copy = LocalDict(
            {
                key: copy_value(key, value)
                for key, value in self.items()
                if should_include(key)
            }
        )
        for call in on_done_calls:
            call(self, copy, True, thread_name)
        return copy

    def copy_to_new_task(self, task_name: str) -> LocalDict:
        on_done_calls = []

        def should_include(t: type | str):
            config = get_copy_behavior(t) or DEFAULT_CONFIG
            if on_done := config.on_copy_done:
                on_done_calls.append(on_done)
            return config.copy_to_task

        copy = LocalDict(
            {
                key: copy_value(key, value)
                for key, value in self.items()
                if should_include(key)
            }
        )
        for call in on_done_calls:
            call(self, copy, False, task_name)
        return copy


_context_dict: ContextVar[LocalDict] = ContextVar(f"{__name__}.LocalDict")


def get_context_dict() -> LocalDict:
    try:
        local_dict = _context_dict.get()
    except LookupError:
        local_dict = LocalDict()
        _context_dict.set(local_dict)
        return local_dict
    if local_dict is ...:
        local_dict = LocalDict()
        _context_dict.set(local_dict)
    return local_dict


def set_context_dict(context_dict: LocalDict):
    _context_dict.set(context_dict)


def force_new_context_dict_on_task(task_name: str = "unknown"):
    old = get_context_dict()
    new = old.copy_to_new_task(task_name)
    set_context_dict(new)


def create_task_copy_context(awaitable: Coroutine) -> Task:
    old = get_context_dict()
    task_name = as_name(awaitable)
    new = old.copy_to_new_task(task_name)

    def start_task():
        set_context_dict(new)
        return create_task(awaitable)

    return Context().run(start_task)


def clear_context_dict():
    """Ideally we would _context.dict.reset(token) but we have no token But
    this is usually only needed for testing."""
    try:
        old = _context_dict.get()
    except LookupError:
        return
    if old is ...:
        return
    _context_dict.set(...)


def get_context_instance(t: type[T]) -> T:
    return get_context_dict().get_instance(t)


def get_context_instance_or_none(t: type[T]) -> T | None:
    with suppress(KeyError):
        return get_context_instance(t)


def set_context_instance(t: T) -> T | None:
    return get_context_dict().set_instance(t)


def pop_context_instance(t: type[T]) -> T | None:
    return get_context_dict().pop_instance(t)
