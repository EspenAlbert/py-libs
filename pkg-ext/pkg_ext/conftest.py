from pathlib import Path

import pytest

REPO_PATH = Path(__file__).parent.parent.parent
assert (REPO_PATH / ".git").exists()
TEST_DATA_PATH = Path(__file__).parent / "testdata"


@pytest.fixture()
def repo_path() -> Path:
    return REPO_PATH


@pytest.fixture()
def coverage_xml_test() -> Path:
    return TEST_DATA_PATH / "coverage.xml"
