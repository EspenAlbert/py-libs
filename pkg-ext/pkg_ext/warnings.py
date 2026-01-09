"""Custom warning classes and decorators for pkg-ext stability levels."""

import warnings
from functools import wraps
from inspect import signature
from typing import Any, Callable, TypeVar, overload
from warnings import deprecated  # noqa: F401 - re-export for convenience

F = TypeVar("F", bound=Callable[..., Any])


def _get_arg_names(func: Callable) -> set[str]:
    return {p.name for p in signature(func).parameters.values() if p.name != "self"}


def _validate_arg_names(func: Callable, names: set[str], context: str) -> None:
    valid_names = _get_arg_names(func)
    invalid = names - valid_names
    if invalid:
        raise ValueError(
            f"{context}: {invalid} not in {func.__name__} signature {valid_names}"
        )


class PkgExtWarning(UserWarning):
    """Base warning class for pkg-ext."""


class PkgExtExperimentalWarning(PkgExtWarning):
    """Warning for experimental features."""


class PkgExtDeprecationWarning(PkgExtWarning, DeprecationWarning):
    """Warning for deprecated features."""


def warn_experimental(feature_name: str, *, stacklevel: int = 2) -> None:
    warnings.warn(
        f"'{feature_name}' is experimental and may change in future versions.",
        category=PkgExtExperimentalWarning,
        stacklevel=stacklevel,
    )


def warn_deprecated(
    old_name: str,
    new_name: str | None = None,
    *,
    stacklevel: int = 2,
) -> None:
    msg = f"'{old_name}' is deprecated"
    msg += f", use '{new_name}' instead." if new_name else "."
    warnings.warn(msg, category=PkgExtDeprecationWarning, stacklevel=stacklevel)


@overload
def experimental(obj: type) -> type: ...
@overload
def experimental(obj: F) -> F: ...


def experimental(obj: type | F) -> type | F:
    if isinstance(obj, type):
        original_init = obj.__init__

        @wraps(original_init)
        def wrapped_init(self: Any, *args: Any, **kwargs: Any) -> None:
            warn_experimental(obj.__name__, stacklevel=2)
            original_init(self, *args, **kwargs)

        obj.__init__ = wrapped_init  # type: ignore[method-assign]
        return obj

    @wraps(obj)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        warn_experimental(obj.__name__, stacklevel=2)
        return obj(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def experimental_args(*names: str) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        _validate_arg_names(func, set(names), "@experimental_args")

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for name in names:
                if name in kwargs:
                    warnings.warn(
                        f"Argument '{name}' is experimental and may change in future versions.",
                        category=PkgExtExperimentalWarning,
                        stacklevel=2,
                    )
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def deprecated_args(*names: str, **renames: str) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        all_names = set(names) | set(renames.keys()) | set(renames.values())
        _validate_arg_names(func, all_names, "@deprecated_args")

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for name in names:
                if name in kwargs:
                    warnings.warn(
                        f"Argument '{name}' is deprecated.",
                        category=PkgExtDeprecationWarning,
                        stacklevel=2,
                    )
            for old_name, new_name in renames.items():
                if old_name in kwargs:
                    warnings.warn(
                        f"Argument '{old_name}' is deprecated, use '{new_name}' instead.",
                        category=PkgExtDeprecationWarning,
                        stacklevel=2,
                    )
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def deprecated_arg(
    name: str,
    *,
    new_name: str | None = None,
    reason: str | None = None,
) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        to_validate = {name, new_name} - {None}
        _validate_arg_names(func, to_validate, "@deprecated_arg")  # type: ignore[arg-type]

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if name in kwargs:
                msg = f"Argument '{name}' is deprecated"
                if new_name:
                    msg += f", use '{new_name}' instead"
                if reason:
                    msg += f": {reason}"
                elif not new_name:
                    msg += "."
                warnings.warn(msg, category=PkgExtDeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
