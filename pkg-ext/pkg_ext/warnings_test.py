import warnings

import pytest

from pkg_ext.warnings import (
    PkgExtDeprecationWarning,
    PkgExtExperimentalWarning,
    PkgExtWarning,
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
