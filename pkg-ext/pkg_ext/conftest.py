import re
from pathlib import Path
from typing import Protocol

import pytest
from zero_3rdparty.str_utils import ensure_prefix

REPO_PATH = Path(__file__).parent.parent.parent
assert (REPO_PATH / ".git").exists()
TEST_DATA_PATH = Path(__file__).parent / "testdata"


@pytest.fixture()
def repo_path() -> Path:
    return REPO_PATH


@pytest.fixture()
def coverage_xml_test() -> Path:
    return TEST_DATA_PATH / "coverage.xml"


class LocalRegressionCheck(Protocol):
    def __call__(self, text: str, extension: str): ...


@pytest.fixture()
def file_regression_testdata(file_regression, request) -> LocalRegressionCheck:
    basename = re.sub(r"[\W]", "_", request.node.name)

    def local_regression_check(text: str, extension: str):
        dotted_extension = ensure_prefix(extension, ".")
        path = TEST_DATA_PATH / f"{basename}{dotted_extension}"
        return file_regression.check(text, fullpath=path)

    return local_regression_check
