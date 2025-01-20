import pytest
import xdoctest as xdoc  # type: ignore

from model_lib import (
    base_settings,
    constants,
    dump_functions,
    errors,
    model_base,
    model_dump,
    pydantic_utils,
)
from model_lib.metadata import context_dict, metadata, metadata_dump, metadata_fields
from model_lib.serialize import base_64, json_serialize, parse, yaml_serialize


@pytest.mark.parametrize(
    "module",
    [
        base_settings,
        constants,
        dump_functions,
        errors,
        model_base,
        model_dump,
        pydantic_utils,
        context_dict,
        metadata,
        metadata_dump,
        metadata_fields,
        base_64,
        json_serialize,
        parse,
        yaml_serialize,
    ],
)
def test_model_lib_doctests(module):
    return_code = xdoc.doctest_module(module.__file__, command="all", verbose=1)
    assert not return_code["failed"]
