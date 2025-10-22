from pathlib import Path
from typing import ClassVar, Self, TypeVar

from model_lib.serialize.parse import parse_model
from pydantic import DirectoryPath, Field, model_validator
from pydantic_settings import BaseSettings
from zero_3rdparty import file_utils

from pkg_ext.config import ProjectConfig, load_project_config, load_user_config

T = TypeVar("T")


def default_commit_fix_prefixes() -> tuple[str, ...]:
    return ("fix:",)


def default_commit_diff_suffixes() -> tuple[str, ...]:
    return (".py",)


class PkgSettings(BaseSettings):
    PUBLIC_GROUPS_STORAGE_FILENAME: ClassVar[str] = ".groups.yaml"
    CHANGELOG_FILENAME: ClassVar[str] = "CHANGELOG.md"
    CHANGELOG_DIR_NAME: ClassVar[str] = ".changelog"

    after_file_write_hooks: tuple[str, ...] | None = Field(default=None)
    changelog_cleanup_count: int = Field(
        default=ProjectConfig.DEFAULT_CHANGELOG_CLEANUP_COUNT,
        description="If the .changelog reach more than `changelog_cleanup_count` post-merge we will add an extra commit cleaning up the old entries. We archive the `changelog_cleanup_count` - `changelog_keep_count` to directories.",
    )
    changelog_keep_count: int = Field(
        default=ProjectConfig.DEFAULT_CHANGELOG_KEEP_COUNT,
        description="When the changelog is cleaned, how many entries are kept?",
    )
    commit_fix_diff_suffixes: tuple[str, ...] = Field(
        default_factory=default_commit_diff_suffixes
    )
    commit_fix_prefixes: tuple[str, ...] = Field(
        default_factory=default_commit_fix_prefixes
    )
    dev_mode: bool = False
    file_header: str = Field(
        default=ProjectConfig.DEFAULT_FILE_HEADER,
        description="Added to the top of each generated file.",
    )
    is_bot: bool = False
    pkg_directory: DirectoryPath
    repo_root: DirectoryPath
    skip_open_in_editor: bool = False
    tag_prefix: str = ""

    def _with_dev_suffix(self, path: Path) -> Path:
        if self.dev_mode:
            return path.with_stem(f"{path.stem}-dev")
        return path

    def _without_dev_suffix(self, path: Path) -> Path:
        return path.with_stem(path.stem.replace("-dev", ""))

    @model_validator(mode="after")
    def check_paths(self) -> Self:
        assert self.pkg_directory.exists(), (
            f"Package directory does not exist: {self.pkg_directory}"
        )
        assert self.init_path.exists(), f"Init path does not exist: {self.init_path}"
        if self.is_bot:
            self.skip_open_in_editor = True
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
    def changelog_dir(self) -> DirectoryPath:
        return self.state_dir / self.CHANGELOG_DIR_NAME

    @property
    def changelog_md(self) -> Path:
        return self._with_dev_suffix(self.state_dir / self.CHANGELOG_FILENAME)

    @property
    def public_groups_path(self) -> Path:
        return self._with_dev_suffix(
            self.state_dir / self.PUBLIC_GROUPS_STORAGE_FILENAME
        )

    @property
    def pyproject_toml(self) -> Path:
        return self.state_dir / "pyproject.toml"

    def force_bot(self) -> None:
        self.is_bot = True
        self.skip_open_in_editor = True

    def parse_computed_public_groups(self, t: type[T]) -> T:
        from pkg_ext.models import PublicGroups  # avoid dependency

        assert t is PublicGroups

        public_groups_path = self.public_groups_path
        no_suffix_path = self._without_dev_suffix(public_groups_path)
        if self.dev_mode and no_suffix_path.exists():
            file_utils.copy(no_suffix_path, public_groups_path)
        if public_groups_path.exists():
            public_groups = parse_model(public_groups_path, t=PublicGroups)
            public_groups.storage_path = public_groups_path
        else:
            public_groups = PublicGroups(storage_path=public_groups_path)
        return public_groups  # type: ignore


def pkg_settings(
    repo_root: Path,
    pkg_path: str,
    *,
    skip_open_in_editor: bool | None = None,
    is_bot: bool = False,
    dev_mode: bool = False,
    tag_prefix: str | None = None,
    file_header: str | None = None,
    commit_fix_prefixes: tuple[str, ...] | None = None,
    commit_fix_diff_suffixes: tuple[str, ...] | None = None,
    after_file_write_hooks: tuple[str, ...] | None = None,
) -> PkgSettings:
    # Resolve global settings with proper precedence: CLI arg → Env var → Config file(user or proejct) → Default
    user_config = load_user_config()
    project_config = load_project_config((repo_root / pkg_path).parent)

    return PkgSettings(
        repo_root=repo_root,
        is_bot=is_bot,
        pkg_directory=repo_root / pkg_path,
        skip_open_in_editor=skip_open_in_editor
        if skip_open_in_editor is not None
        else user_config.skip_open_in_editor,
        dev_mode=dev_mode,
        file_header=file_header or project_config.file_header,
        commit_fix_prefixes=commit_fix_prefixes or project_config.commit_fix_prefixes,
        commit_fix_diff_suffixes=commit_fix_diff_suffixes
        or project_config.commit_diff_suffixes,
        after_file_write_hooks=after_file_write_hooks
        if after_file_write_hooks is not None
        else project_config.after_file_write_hooks,
        tag_prefix=tag_prefix if tag_prefix is not None else project_config.tag_prefix,
        changelog_cleanup_count=project_config.changelog_cleanup_count,
        changelog_keep_count=project_config.changelog_keep_count,
    )
