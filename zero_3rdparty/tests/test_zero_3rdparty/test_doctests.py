from types import ModuleType
from typing import Callable
from zero_3rdparty import (
    datetime_utils,
    dict_nested,
    dict_utils,
    env_reader,
    file_utils,
    id_creator,
    iter_utils,
    object_name,
    str_utils,

)

import pytest
import xdoctest as xdoc  # type: ignore


def doctest_modules(modules: list[ModuleType]):
    def decorator(_: Callable):
        @pytest.mark.parametrize("module", modules)
        def test_doctests(module):
            return_code = xdoc.doctest_module(module.__file__, command="all")
            assert not return_code["failed"]

        return test_doctests

    return decorator

@doctest_modules(
    [
        datetime_utils,
        dict_nested,
        dict_utils,
        env_reader,
        file_utils,
        id_creator,
        iter_utils,
        object_name,
        str_utils,
    ]
)
def test_devops_doctests():
    pass
