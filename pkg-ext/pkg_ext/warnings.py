"""Custom warning classes and decorators for pkg-ext stability levels."""

import warnings
from functools import wraps
from typing import Any, Callable, TypeVar, overload
from warnings import deprecated  # noqa: F401 - re-export for convenience

F = TypeVar("F", bound=Callable[..., Any])


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
