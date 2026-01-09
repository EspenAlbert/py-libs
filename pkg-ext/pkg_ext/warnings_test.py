import warnings

import pytest

from pkg_ext.warnings import (
    PkgExtDeprecationWarning,
    PkgExtExperimentalWarning,
    PkgExtWarning,
    deprecated,
    experimental,
    warn_deprecated,
    warn_experimental,
)


def test_warning_hierarchy():
    assert issubclass(PkgExtExperimentalWarning, PkgExtWarning)
    assert issubclass(PkgExtDeprecationWarning, PkgExtWarning)
    assert issubclass(PkgExtDeprecationWarning, DeprecationWarning)
    assert issubclass(PkgExtWarning, UserWarning)


def test_warn_experimental():
    with pytest.warns(PkgExtExperimentalWarning, match="'my_feature' is experimental"):
        warn_experimental("my_feature")


def test_warn_deprecated_with_replacement():
    with pytest.warns(
        PkgExtDeprecationWarning, match="'old_func' is deprecated, use 'new_func'"
    ):
        warn_deprecated("old_func", "new_func")


def test_warn_deprecated_without_replacement():
    with pytest.warns(PkgExtDeprecationWarning, match="'old_func' is deprecated.$"):
        warn_deprecated("old_func")


def test_suppress_by_base_class():
    with warnings.catch_warnings(record=True) as w:
        warnings.filterwarnings("ignore", category=PkgExtWarning)
        warn_experimental("feat1")
        warn_deprecated("feat2")
        assert len(w) == 0


def test_suppress_specific_class_only():
    with warnings.catch_warnings(record=True) as w:
        warnings.filterwarnings("always")
        warnings.filterwarnings("ignore", category=PkgExtExperimentalWarning)
        warn_experimental("feat1")
        warn_deprecated("feat2")
        assert len(w) == 1
        assert issubclass(w[0].category, PkgExtDeprecationWarning)


def test_experimental_decorator_on_function():
    @experimental
    def my_func() -> str:
        return "result"

    with pytest.warns(PkgExtExperimentalWarning, match="'my_func' is experimental"):
        result = my_func()
    assert result == "result"


def test_experimental_decorator_on_class():
    @experimental
    class MyClass:
        def __init__(self, value: int) -> None:
            self.value = value

    with pytest.warns(PkgExtExperimentalWarning, match="'MyClass' is experimental"):
        obj = MyClass(42)
    assert obj.value == 42


def test_experimental_preserves_function_metadata():
    @experimental
    def documented_func() -> None:
        """My docstring."""

    assert documented_func.__name__ == "documented_func"
    assert documented_func.__doc__ == "My docstring."


def test_deprecated_reexport():
    @deprecated("Use new_func instead")
    def old_func() -> str:
        return "old"

    with pytest.warns(DeprecationWarning, match="Use new_func instead"):
        result = old_func()
    assert result == "old"
