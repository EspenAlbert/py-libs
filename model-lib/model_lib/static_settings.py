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
