from functools import wraps

from zero_3rdparty.decorator_globals import is_decorated, mark_as_decorated

_STATIC_RETURN_MESSAGE = "returned from decorator"


def _my_decorator(func):
    if is_decorated(_my_decorator, func):
        return func

    @wraps(func)
    def inner(*args, **kwargs):
        return _STATIC_RETURN_MESSAGE

    return inner


def _my_func(some_arg: str):
    return some_arg


@_my_decorator
def _already_decorated(some_arg):
    return some_arg


def test_marking_function_as_decorated():
    assert _my_func("ok") == "ok"
    assert is_decorated(_my_decorator, _my_func) is False
    mark_as_decorated(_my_decorator, _my_func)
    assert is_decorated(_my_decorator, _my_func) is True
    assert _my_decorator(_my_func)("ok") == "ok"


def test_already_decorated_is_decorated():
    assert _already_decorated("any") == _STATIC_RETURN_MESSAGE
