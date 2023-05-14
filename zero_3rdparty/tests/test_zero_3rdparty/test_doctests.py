import pytest
import xdoctest as xdoc  # type: ignore

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


@pytest.mark.parametrize(
    "module",
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
    ],
)
def test_zero_3rdparty_doctests(module):
    return_code = xdoc.doctest_module(module.__file__, command="all", verbose=1)
    assert not return_code["failed"]
