import pytest
import xdoctest as xdoc  # type: ignore

from compose_chart_export import (
    chart_combiner,
    chart_file_templates,
    chart_mods,
    chart_read,
    compose_export,
    ports,
    settings,
)


@pytest.mark.parametrize(
    "module",
    [
        chart_combiner,
        chart_mods,
        chart_read,
        ports,
        chart_file_templates,
        compose_export,
        settings,
    ],
)
def test_chart_export_doctests(module):
    return_code = xdoc.doctest_module(module.__file__, command="all", verbose=1)
    assert not return_code["failed"]
