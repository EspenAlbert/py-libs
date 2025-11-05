from unittest.mock import MagicMock

from zero_3rdparty.file_utils import ensure_parents_write_text

from pkg_ext.generation.pyproject import update_pyproject_toml

_pyproject_toml = """\
[project]
name = "pkg-ext"
version = "1.0.0"
requires-python = ">=3.12"
"""


def test_update_pyproject_toml(settings):
    path = settings.pyproject_toml
    ensure_parents_write_text(path, _pyproject_toml)
    update_pyproject_toml(MagicMock(settings=settings), "2.0.0")
    assert 'version = "2.0.0"' in path.read_text()
