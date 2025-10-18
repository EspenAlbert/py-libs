import re
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

import pytest
from model_lib.static_settings import StaticSettings
from pytest_regressions.file_regression import FileRegressionFixture
from zero_3rdparty import file_utils
from zero_3rdparty.file_utils import ensure_parents_write_text
from zero_3rdparty.str_utils import ensure_prefix

from pkg_ext.settings import PkgSettings

REPO_PATH = Path(__file__).parent.parent.parent
assert (REPO_PATH / ".git").exists()
TEST_DATA_PATH = Path(__file__).parent / "testdata"
TEST_PKG_NAME = "my_pkg"
CHANGELOG_YAML_FILENAME = ".changelog.yaml"


@pytest.fixture()
def repo_path() -> Path:
    return REPO_PATH


@pytest.fixture(autouse=True)
def settings(static_env_vars: StaticSettings, tmp_path) -> PkgSettings:
    assert static_env_vars
    pkg_directory = tmp_path / TEST_PKG_NAME
    init_path = pkg_directory / "__init__.py"
    ensure_parents_write_text(init_path, "")
    return PkgSettings(repo_root=tmp_path, pkg_directory=pkg_directory)


@pytest.fixture()
def coverage_xml_test() -> Path:
    return TEST_DATA_PATH / "coverage.xml"


class LocalRegressionCheck(Protocol):
    def __call__(self, text: str, extension: str): ...


@dataclass
class E2eDirs:
    e2e_dir: Path
    e2e_pkg_dir: Path
    tmp_path: Path

    @property
    def execution_e2e_dir(self) -> Path:
        return self.tmp_path / self.e2e_dir.name

    @property
    def execution_e2e_pkg_path(self) -> Path:
        return self.execution_e2e_dir / self.pkg_path_relative

    @property
    def pkg_path_relative(self) -> str:
        return str(self.e2e_pkg_dir.relative_to(self.e2e_dir))

    def python_actual_group_path(self, name: str) -> Path:
        return self.execution_e2e_pkg_path / f"{name}.py"


@pytest.fixture()
def file_regression_testdata(file_regression, request) -> LocalRegressionCheck:
    basename = re.sub(r"[\W]", "_", request.node.name)

    def local_regression_check(text: str, extension: str):
        dotted_extension = ensure_prefix(extension, ".")
        path = TEST_DATA_PATH / f"{basename}{dotted_extension}"
        return file_regression.check(text, fullpath=path)

    return local_regression_check


# 2025-08-30T15-07Z
_ts_regex = re.compile(
    r"(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\.\d+\S+)"
    + "|"
    + r"(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}Z)"
)


def _replace_timestamps(text: str) -> str:
    return _ts_regex.sub("2025-10-18 21:13:06.12345+00:00", text)


# 469fb8
_sha_regex = re.compile(r"[0-9a-f]{6}")


def _replace_shas(text: str) -> str:
    return _sha_regex.sub("GIT_SHA", text)


@pytest.fixture()
def text_normalizer_regression(file_regression) -> Callable[[Path], None]:
    def replace(text: str) -> str:
        text = _replace_timestamps(text)
        return _replace_shas(text)

    def check(path: Path):
        text = path.read_text()
        text = replace(text)
        file_regression.check(text, extension=path.suffix)

    return check


@dataclass
class E2eRegressionCheck:
    e2e_dirs: E2eDirs
    file_regression: FileRegressionFixture

    def _actual_text_modifier(self, text: str, path: Path) -> str:
        if path.name == CHANGELOG_YAML_FILENAME:
            text = re.sub(r"(short_sha: )('?[0-9a-f]+'?)", "short_sha: GIT_SHA", text)
        text = _replace_timestamps(text)
        return _replace_shas(text)

    def modify_files(self, dir_path: Path):
        for file in file_utils.iter_paths(
            dir_path, "*", exclude_folder_names=[".git", "__pycache__"]
        ):
            if not file.is_file():
                continue
            old = file.read_text()
            new = self._actual_text_modifier(old, file)
            if old != new:
                file.write_text(new)

    def check_path(self, actual_path: Path):
        parent = actual_path.parent
        dir_files = [f.name for f in parent.glob("*") if f.is_file()]
        assert actual_path.exists(), (
            f"path not found: {actual_path}, parent_dir={dir_files}"
        )
        relative_path = str(actual_path.relative_to(self.e2e_dirs.execution_e2e_dir))
        expected_path = self.e2e_dirs.e2e_dir / relative_path
        self.file_regression.check(actual_path.read_text(), fullpath=expected_path)

    def __call__(self, rel_path: str, text: str, extension: str):
        dotted_extension = ensure_prefix(extension, ".")
        path = self.e2e_dirs.e2e_dir / rel_path
        self.file_regression.check(
            path.read_text(), fullpath=path, extension=dotted_extension
        )


@pytest.fixture()
def _e2e_dir(request) -> Path:
    dir_name = re.sub(r"[\W]", "_", request.node.name).removeprefix("test_")
    return TEST_DATA_PATH / "e2e" / dir_name


@pytest.fixture()
def _e2e_pkg_path(_e2e_dir) -> Path:  # type: ignore
    yield _e2e_dir / TEST_PKG_NAME  # type: ignore
    del sys.modules[TEST_PKG_NAME]  # support re-importing in the next test
    with suppress(KeyError):
        del sys.modules[f"{TEST_PKG_NAME}._internal"]


@pytest.fixture()
def e2e_dirs(tmp_path, _e2e_dir, _e2e_pkg_path):
    return E2eDirs(_e2e_dir, _e2e_pkg_path, tmp_path)


@pytest.fixture()
def file_regression_e2e(file_regression, e2e_dirs) -> E2eRegressionCheck:  # type: ignore
    yield E2eRegressionCheck(e2e_dirs, file_regression)  # type: ignore
