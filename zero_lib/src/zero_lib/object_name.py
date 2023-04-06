"""FILE FROM mode.utils.objects but modified."""
import logging
import sys
from collections.abc import Awaitable as ColAwaitable
from functools import lru_cache, partial
from inspect import Parameter, currentframe, isclass, signature
from pathlib import Path
from types import FrameType
from typing import Callable, Iterable, Type, TypeVar, Union, cast, get_type_hints

from zero_lib.iter_utils import first

logger = logging.getLogger(__name__)


def _name(obj: Union[Type[object], object]) -> str:
    """Get object qualified name."""
    if not hasattr(obj, "__name__") and hasattr(obj, "__class__"):
        obj = obj.__class__

    name = getattr(obj, "__qualname__", cast(Type[object], obj).__name__)
    module_name = getattr(obj, "__module__", "")
    if not module_name and isinstance(obj, ColAwaitable):
        module_name = obj.cr_frame.f_globals["__name__"]
    return ".".join((module_name or "__module__", name))


def short_name(obj: Union[Type[object], object]) -> str:
    _name = as_name(obj)
    if "." in _name:
        return _name.rsplit(".", maxsplit=1)[1]
    return _name


def as_name(obj: Union[Type[object], object]) -> str:
    """Get non-qualified name of obj, resolve real name of ``__main__``.
    Examples.

    >>> class A:
    ...     pass
    >>> as_name(A).endswith('object_name.A')
    True
    >>> from functools import partial
    >>> partial_name = as_name(partial(A, 'lol'))
    >>> "partial" in partial_name
    True
    >>> partial_name.endswith("object_name.A args: ('lol',), kwargs: {}")
    True
    >>> async def b(s: str):
    ...     pass
    >>> as_name(b).endswith('object_name.b')
    True
    """
    name_ = _name(obj)
    if name_ == "functools.partial":
        if isinstance(obj, partial):
            return (
                f"partial: {as_name(obj.func)} args: {obj.args}, kwargs: {obj.keywords}"
            )
    parts = name_.split(".")
    if parts[0] == "__main__":
        return ".".join([_detect_main_name()] + parts[1:])
    return name_


@lru_cache(maxsize=1)
def _detect_main_name() -> str:  # pragma: no cover
    try:
        filename = sys.modules["__main__"].__file__
    except (AttributeError, KeyError):  # ipython/REPL
        return "__main__"
    else:
        path = Path(filename).absolute()
        node = path.parent
        seen = []
        while node:
            if (node / "__init__.py").exists():
                seen.append(node.stem)
                node = node.parent
            else:
                break
        return ".".join(seen + [path.stem])


def func_arg_names(
    func: Callable, skip_self: bool = True, skip_kwargs: bool = True
) -> list[str]:
    def filter(param: Parameter) -> bool:
        if skip_self and param.name == "self":
            return False
        if skip_kwargs and param.kind == param.VAR_KEYWORD:
            return False
        return True

    return [
        param.name for param in signature(func).parameters.values() if filter(param)
    ]


def func_arg_types(func: Callable) -> list[Type]:
    param_types = [
        value for _name, value in get_type_hints(func).items() if _name != "return"
    ]
    func_name = as_name(func)
    assert len(param_types) == len(
        func_arg_names(func, skip_self=True, skip_kwargs=True)
    ), f"missing type hints on {func_name}"
    return param_types


def call_signature(func, args=None, kwargs=None):
    args = args or tuple()
    kwargs = kwargs or {}
    key_value_str = ",".join(f"{k}={v}" for k, v in kwargs.items())
    function_name = as_name(func)
    return f"{function_name}({args}, {key_value_str})"


def func_arg_name_of_type(
    func: Callable, arg_type: Type, strict: bool = True
) -> str | None:
    for name, value in get_type_hints(func).items():
        if value is arg_type or (not strict and is_subclass(value, arg_type)):
            return name


def is_subclass(maybe_class, classes) -> bool:
    return isclass(maybe_class) and issubclass(maybe_class, classes)


T = TypeVar("T")


def func_args_of_instance(func: Callable, arg_type: Type[T]) -> Iterable[tuple[str, T]]:
    for name, value in get_type_hints(func).items():
        if isinstance(value, arg_type):
            yield name, value


def func_args_of_instance_or_type(
    func: Callable, arg_type: Type[T]
) -> Iterable[tuple[str, Union[T, Type[T]]]]:
    for name, value in get_type_hints(func).items():
        if isinstance(value, arg_type):
            yield name, value
        elif is_subclass(value, arg_type):
            yield name, value


def func_return_type(func: Callable) -> Type | None:
    return get_type_hints(func).get("return", None)


def func_default_instances(
    func: Callable, default_type: Type[T]
) -> Iterable[tuple[str, T]]:
    for name, parameter in signature(func).parameters.items():
        if isinstance(parameter.default, default_type):
            yield name, parameter.default


def func_default_instances_or_classes(
    func: Callable, default_type: Type[T]
) -> Iterable[tuple[str, Union[T, Type[T]]]]:
    for name, parameter in signature(func).parameters.items():
        default = parameter.default
        if isinstance(default, default_type):
            yield name, default
        elif isclass(default) and issubclass(default, default_type):
            yield name, default


def unpack_optional_or_assume_class(maybe_optional) -> Type | None:
    args = getattr(maybe_optional, "__args__", [])
    if not isclass(maybe_optional) and args and isclass(args[0]):
        return args[0]
    if isclass(maybe_optional):
        return maybe_optional


def unpack_first_arg(function: Callable) -> Type:
    maybe_optional = first(func_arg_types(function))
    unpacked = unpack_optional_or_assume_class(maybe_optional)
    assert unpacked is not None, f"unable to find cls for {function}"
    return unpacked


def as_caller_name(frames_back: int = 2, with_line_no: bool = False) -> str:
    frame: FrameType = currentframe()
    for _ in range(frames_back):
        frame = frame.f_back
    code = frame.f_code
    if self := frame.f_locals.get("self"):
        name = f"{self.__class__.__name__}.{code.co_name}"
    else:
        name = code.co_name
    if with_line_no:
        return f"{name}.{frame.f_lineno}"
    return name


def caller_module_and_name() -> tuple[str, str]:
    code: FrameType = currentframe().f_back.f_back
    module = code.f_globals["__name__"]
    if self := code.f_locals.get("self"):
        return module, f"{self.__class__.__name__}.{code.f_code.co_name}"
    return module, code.f_code.co_name


def caller_module_name_line_no_path() -> tuple[str, str, int, str]:
    code: FrameType = currentframe().f_back.f_back
    module = code.f_globals["__name__"]
    path = code.f_globals["__file__"]
    if self := code.f_locals.get("self"):
        return (
            module,
            f"{self.__class__.__name__}.{code.f_code.co_name}",
            code.f_lineno,
            path,
        )
    return module, code.f_code.co_name, code.f_lineno, path
