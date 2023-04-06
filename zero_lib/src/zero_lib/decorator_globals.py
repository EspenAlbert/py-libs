"""Context: store a global dictionary for decorators and use it for checking
if a function is decorated or not.
Can be used to skip decorating by using mark_as_decorator
And in the decorator itself use the is_decorator? return func else decorate(func)
"""
from typing import TypeVar

from zero_lib.object_name import as_name

T = TypeVar("T")


def mark_as_decorated(decorator, func):
    decorator_name = as_name(decorator)
    func_name = as_name(func)
    decorator_cache = globals().setdefault(decorator_name, {})
    decorator_cache[func_name] = True


def is_decorated(decorator, func) -> bool:
    decorator_name = as_name(decorator)
    func_name = as_name(func)
    decorator_cache = globals().setdefault(decorator_name, {})
    return decorator_cache.get(func_name, False)
