from os import getenv
from pathlib import Path
from typing import Self

from pydantic import DirectoryPath, model_validator
from pydantic_settings import BaseSettings


def get_editor() -> str:
    return getenv("EDITOR", "code")


class PkgSettings(BaseSettings):
    repo_root: DirectoryPath
    pkg_directory: DirectoryPath

    @model_validator(mode="after")
    def check_paths(self) -> Self:
        assert self.pkg_directory.exists()
        assert self.init_path.exists()
        return self

    @property
    def init_path(self) -> Path:
        return self.pkg_directory / "__init__.py"

    @property
    def pkg_import_name(self) -> str:
        return self.pkg_directory.name

    @property
    def state_dir(self) -> DirectoryPath:
        return self.pkg_directory.parent

    @property
    def changelog_path(self) -> DirectoryPath:
        return self.state_dir / ".changelog"


def pkg_settings(repo_root: Path, pkg_path: str) -> PkgSettings:
    return PkgSettings(repo_root=repo_root, pkg_directory=repo_root / pkg_path)
