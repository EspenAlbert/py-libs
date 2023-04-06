from __future__ import annotations

from collections import defaultdict
from functools import wraps
from inspect import signature
from time import monotonic
from typing import Any, Callable, Hashable, TypeVar

T = TypeVar("T")
_sentinel = object()


def _wrap_func(func, seconds):
    expire_result = (0, _sentinel)

    @wraps(func)
    def inner(*args, **kwargs):
        nonlocal expire_result
        now_seconds = monotonic()
        expire, call_result = expire_result
        if now_seconds < expire and call_result is not _sentinel:
            return call_result
        call_result = func(*args, **kwargs)
        expire_result = (now_seconds + seconds, call_result)
        return call_result

    def clear():
        nonlocal expire_result
        expire_result = (0, _sentinel)

    inner.clear = clear
    return inner


def _wrap_method(
    seconds: float, instance_key: Callable[[T], Hashable], meth: Callable[[T, ...], Any]
):
    expire_times = defaultdict(lambda: (0, _sentinel))

    @wraps(meth)
    def inner(self, *args, **kwargs):
        now_seconds = monotonic()
        key = instance_key(self)
        expire, call_result = expire_times[key]
        if now_seconds < expire and call_result is not _sentinel:
            return call_result
        call_result = meth(self, *args, **kwargs)
        expire_times[key] = now_seconds + seconds, call_result
        return call_result

    def clear():
        nonlocal expire_times
        keys = list(expire_times.keys())
        for key in keys:
            expire_times[key] = (0, _sentinel)

    inner.clear = clear
    return inner


def cache_ttl(seconds: float | int) -> Callable[[T], T]:
    """simple decorator if you want to cache the results of a call ignoring arguments
    Warning:
        1. Only caches a 'single value'
        2. Expects it to be a method if 'self' is in parameters
    '"""
    assert isinstance(seconds, (float, int)), "ttl seconds must be int/float"

    def decorator(func: T) -> T:
        if "self" in signature(func).parameters:
            return _wrap_method(seconds, id, func)
        return _wrap_func(func, seconds)

    return decorator


def clear_cache(func):
    func.clear()
