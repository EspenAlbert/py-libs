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


class E2eRegressionCheck(Protocol):
    def __call__(self, rel_path: str, text: str, extension: str): ...


@pytest.fixture()
def e2e_dir(request) -> Path:
    dir_name = re.sub(r"[\W]", "_", request.node.name).removeprefix("test_")
    return TEST_DATA_PATH / "e2e" / dir_name


@pytest.fixture()
def e2e_pkg_path(e2e_dir) -> Path:
    return e2e_dir / "my_pkg"


@pytest.fixture()
def file_regression_e2e(file_regression, e2e_dir) -> E2eRegressionCheck:
    def local_regression_check(rel_path: str, text: str, extension: str):
        dotted_extension = ensure_prefix(extension, ".")
        path = e2e_dir / rel_path
        return file_regression.check(text, fullpath=path, extension=dotted_extension)

    return local_regression_check
