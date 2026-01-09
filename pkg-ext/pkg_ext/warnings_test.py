import warnings

import pytest

from pkg_ext.warnings import (
    PkgExtDeprecationWarning,
    PkgExtExperimentalWarning,
    PkgExtWarning,
    deprecated,
    deprecated_arg,
    deprecated_args,
    experimental,
    experimental_args,
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


def test_experimental_args_warns_when_passed():
    @experimental_args("new_opt")
    def func(x: int, new_opt: str | None = None) -> int:
        return x

    with pytest.warns(
        PkgExtExperimentalWarning, match="Argument 'new_opt' is experimental"
    ):
        func(1, new_opt="test")


def test_experimental_args_no_warning_when_not_passed():
    @experimental_args("new_opt")
    def func(x: int, new_opt: str | None = None) -> int:
        return x

    with warnings.catch_warnings(record=True) as w:
        warnings.filterwarnings("always")
        result = func(1)
        assert result == 1
        assert len(w) == 0


def test_experimental_args_multiple():
    @experimental_args("a", "b")
    def func(a: int | None = None, b: int | None = None) -> None:
        pass

    with warnings.catch_warnings(record=True) as w:
        warnings.filterwarnings("always")
        func(a=1, b=2)
        assert len(w) == 2


def test_deprecated_args_simple():
    @deprecated_args("old_opt")
    def func(old_opt: str | None = None) -> None:
        pass

    with pytest.warns(
        PkgExtDeprecationWarning, match="Argument 'old_opt' is deprecated."
    ):
        func(old_opt="x")


def test_deprecated_args_rename_mapping():
    @deprecated_args(old_format="format")
    def func(format: str = "json", old_format: str | None = None) -> None:
        pass

    with pytest.warns(PkgExtDeprecationWarning, match="use 'format' instead"):
        func(old_format="xml")


def test_deprecated_arg_with_reason():
    @deprecated_arg("unsafe", reason="security vulnerability")
    def func(unsafe: bool = False) -> None:
        pass

    with pytest.warns(PkgExtDeprecationWarning, match="security vulnerability"):
        func(unsafe=True)


def test_deprecated_arg_with_new_name_and_reason():
    @deprecated_arg("cb", new_name="on_done", reason="renamed for clarity")
    def func(cb: None = None, on_done: None = None) -> None:
        pass

    with pytest.warns(PkgExtDeprecationWarning, match="use 'on_done' instead.*renamed"):
        func(cb=None)


def test_args_decorators_preserve_metadata():
    @experimental_args("x")
    def my_func(x: int | None = None) -> None:
        """Docstring."""

    assert my_func.__name__ == "my_func"
    assert my_func.__doc__ == "Docstring."


def test_stacked_deprecated_arg_decorators():
    @deprecated_arg("a", reason="removed")
    @deprecated_arg("b", new_name="c")
    def func(a: int | None = None, b: int | None = None, c: int | None = None) -> None:
        pass

    with warnings.catch_warnings(record=True) as w:
        warnings.filterwarnings("always")
        func(a=1, b=2)
        assert len(w) == 2
        messages = [str(x.message) for x in w]
        assert any("removed" in m for m in messages)
        assert any("use 'c'" in m for m in messages)


def test_validation_rejects_invalid_arg_names():
    with pytest.raises(ValueError, match="nonexistent"):

        @experimental_args("nonexistent")
        def f1(x: int | None = None) -> None:
            pass


def test_validation_rejects_invalid_new_name():
    with pytest.raises(ValueError, match="invalid_target"):

        @deprecated_arg("a", new_name="invalid_target")
        def f2(a: int | None = None) -> None:
            pass
