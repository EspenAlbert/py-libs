"""Custom warning classes for pkg-ext stability levels."""

import warnings


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
