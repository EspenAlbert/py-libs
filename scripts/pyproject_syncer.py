import logging
from pathlib import Path

ROOT_PATH = Path(__file__).parent.parent
template = """\
[project]
name = "{NAME}"
version = "1.0.0+rc1"
requires-python = ">=3.10"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.sdist]
include = [
  "{NAME_UNDERSCORE}/*.py",
]
exclude = [
  "*_test.py",
  "conftest.py",
  "test_*.json",
]
"""

if __name__ == "__main__":
    for project in [
        "ask-shell",
        "model-lib",
        "pkg-ext",
        "pytest-model-lib",
        "zero-3rdparty",
    ]:
        path = ROOT_PATH / project / "pyproject.toml"
        content = template.format(
            NAME=project, NAME_UNDERSCORE=project.replace("-", "_")
        )
        logging.warning(f"Writing to {path}")
        if not path.exists():
            path.write_text(content)
