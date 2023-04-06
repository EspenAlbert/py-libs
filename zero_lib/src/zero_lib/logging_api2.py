from __future__ import annotations

import inspect
import logging
import reprlib
from dataclasses import dataclass
from functools import wraps
from threading import Lock
from typing import Any, Callable, ContextManager, Optional, Protocol, TypeVar

from zero_lib.decorator_globals import is_decorated
from zero_lib.object_name import as_name, func_arg_names, func_arg_types

global_logger = logging.getLogger(__name__)


class LogExtra(Protocol):
    def __call__(self, logger: logging.Logger | None = None, **kwargs) -> Any:
        ...


def _default_log_extra(logger: logging.Logger | None = None, **kwargs):
    logger = logger or global_logger
    logger.info(f"log_extra: {kwargs}")


_log_extra_factory = _default_log_extra
_global_lock = Lock()


def log_extra(
    key: str = "",
    value: Any = None,
    /,
    *,
    logger: logging.Logger | None = None,
    **kwargs,
) -> None:
    if key:
        kwargs[key] = value
    _log_extra_factory(logger, **kwargs)


def set_log_extra(new_factory: LogExtra) -> LogExtra:
    with _global_lock:
        global _log_extra_factory
        old_factory = _log_extra_factory
        _log_extra_factory = new_factory
        return old_factory


class ActionFactory(Protocol):
    def __call__(
        self,
        logger: logging.Logger | None,
        action_name: str,
        extra: dict,
    ) -> ContextManager:
        ...


@dataclass
class _default_action:
    name: str
    logger: logging.Logger
    extra: dict

    def __enter__(self):
        self.logger.info(f"new_action.__enter__ {self.name}, {log_extra}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            self.logger.exception(exc_val)
        self.logger.info(f"new_action.__exit__ {self.name}")


def _default_new_action_factory(
    logger: logging.Logger | None,
    action_name: str,
    extra: dict,
) -> ContextManager:
    return _default_action(
        name=action_name, logger=logger or global_logger, extra=extra
    )


_new_action_factory = _default_new_action_factory


def set_new_action_factory(new_factory: ActionFactory) -> ActionFactory:
    """returns old factory."""
    with _global_lock:
        global _new_action_factory
        old_factory = _new_action_factory
        _new_action_factory = new_factory
        return old_factory


def new_action(
    action_name: str,
    logger: logging.Logger | None = None,
    **kwargs,
) -> ContextManager:
    return _new_action_factory(logger, action_name, kwargs)


T = TypeVar("T")
str_shortener = reprlib.Repr()
str_shortener.maxstring = 120


def log(
    func: Optional[T] = None,
    *,
    logger: logging.Logger | None = None,
    log_full_args: bool = False,
    log_full_response: bool = False,
    action_type: str = "",
    action_type_prefix: str = "",
    skip_self=True,
) -> T:
    def decorator(func: Callable):
        if is_decorated(log, func):
            return func
        nonlocal action_type
        assert callable(func), "@log must be callable"
        func_name = getattr(func, "__qualname__", None) or as_name(func)
        if not action_type:
            action_type = func_name
            if not log_full_args:
                try:
                    event_types = ",".join(cls.__name__ for cls in func_arg_types(func))
                except (
                    AttributeError,
                    AssertionError,
                    ValueError,
                    TypeError,
                    NameError,
                ):
                    event_types = ""
                action_type = f"{func_name}({event_types})"
        if action_type_prefix:
            action_type = action_type_prefix + action_type
        try:
            arg_names = func_arg_names(func, skip_self=False)
        except ValueError:
            # probably builtin, return function as is
            return func
        if "BufferedWriter" in action_type:
            return func
        action_type = str_shortener.repr(action_type)

        def as_action(args: tuple, kwargs: dict) -> ContextManager:
            if log_full_args:
                log_kwargs = dict(zip(arg_names, args)) | kwargs
                if skip_self:
                    log_kwargs.pop("self", None)
                return new_action(action_type, logger=logger, **log_kwargs)
            return new_action(action_type, logger=logger)

        def log_responses(responses: list[object]):
            if log_full_response:
                fields = {
                    f"response_{i}": each_response
                    for i, each_response in enumerate(responses)
                }
                log_extra(**fields)
            elif responses != [None]:
                names = ",".join(type(response).__name__ for response in responses)
                log_extra(responses=names)

        if inspect.isgeneratorfunction(func):

            @wraps(func)
            def inner_generator(*args, **kwargs):
                SKIP_LOCALS = True  # noqa
                with as_action(args, kwargs):
                    responses = list(func(*args, **kwargs))
                    log_responses(responses)
                yield from responses

            return inner_generator
        elif inspect.iscoroutinefunction(func):

            @wraps(func)
            async def a_inner(*args, **kwargs):
                SKIP_LOCALS = True  # noqa
                with as_action(args, kwargs):
                    response = await func(*args, **kwargs)
                    log_responses([response])
                return response

            return a_inner
        elif inspect.isasyncgenfunction(func):

            @wraps(func)
            async def a_inner_gen(*args, **kwargs):
                SKIP_LOCALS = True  # noqa
                with as_action(args, kwargs):
                    responses = [response async for response in func(*args, **kwargs)]
                    log_responses(responses)
                for response in responses:
                    yield response

            return a_inner_gen
        else:

            @wraps(func)
            def inner(*args, **kwargs):
                SKIP_LOCALS = True  # noqa
                with as_action(args, kwargs):
                    response = func(*args, **kwargs)
                    log_responses([response])
                    return response

            return inner

    if func:
        return decorator(func)

    return decorator


class LogEventOrKwargs(Protocol):
    async def __call__(self, event: Any = None, key: str = "", /, **kwargs) -> None:
        ...


async def default_log_event_or_kwargs(
    event: Any = None, key: str = "", /, **kwargs
) -> None:
    if key:
        kwargs[key] = event
    elif event:
        log_extra(event=event)
    if kwargs:
        log_extra(**kwargs)
