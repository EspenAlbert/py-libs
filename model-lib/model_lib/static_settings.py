import tempfile
from pathlib import Path
from typing import Self

from pydantic import DirectoryPath
from pydantic_settings import BaseSettings
from zero_3rdparty import humps


class StaticSettings(BaseSettings):
    STATIC_DIR: DirectoryPath
    CACHE_DIR: DirectoryPath
    SKIP_APP_NAME: bool = False

    @classmethod
    def app_name(cls) -> str:
        return humps.snake_case(cls.__qualname__.removesuffix("Settings"))

    @classmethod
    def for_testing(cls, tmp_path: Path | None = None, **kwargs) -> Self:
        """
        Create a StaticSettings instance for testing purposes.
        """
        tmp_path = tmp_path or Path(tempfile.gettempdir())
        static = tmp_path / "static"
        cache = tmp_path / "cache"
        static.mkdir(parents=True, exist_ok=True)
        cache.mkdir(parents=True, exist_ok=True)
        return cls(STATIC_DIR=static, CACHE_DIR=cache, **kwargs)

    @classmethod
    def from_env(cls, **kwargs) -> Self:
        return cls(**kwargs)  # type: ignore

    @property
    def static_root(self) -> DirectoryPath:
        if self.SKIP_APP_NAME:
            return self.STATIC_DIR
        return self.STATIC_DIR / self.app_name()

    @property
    def cache_root(self) -> DirectoryPath:
        if self.SKIP_APP_NAME:
            return self.CACHE_DIR
        return self.CACHE_DIR / self.app_name()
