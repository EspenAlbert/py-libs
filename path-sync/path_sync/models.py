from __future__ import annotations

import glob as glob_mod
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"


class SyncMode(StrEnum):
    SYNC = "sync"
    REPLACE = "replace"
    SCAFFOLD = "scaffold"


class PathMapping(BaseModel):
    src_path: str
    dest_path: str = ""
    sync_mode: SyncMode = SyncMode.SYNC

    def resolved_dest_path(self) -> str:
        return self.dest_path or self.src_path

    def expand_dest_paths(self, repo_root: Path) -> list[Path]:
        dest_path = self.resolved_dest_path()
        pattern = repo_root / dest_path

        if "*" in dest_path:
            return [Path(p) for p in glob_mod.glob(str(pattern), recursive=True)]
        if pattern.is_dir():
            return [p for p in pattern.rglob("*") if p.is_file()]
        if pattern.exists():
            return [pattern]
        return []


HEADER_TEMPLATE = "path-sync copy -n {config_name}"


class HeaderConfig(BaseModel):
    comment_prefixes: dict[str, str] = Field(default_factory=dict)
    comment_suffixes: dict[str, str] = Field(default_factory=dict)


DEFAULT_BODY_TEMPLATE = """\
Synced from [{src_repo_name}]({src_repo_url}) @ `{src_sha_short}`

<details>
<summary>Sync Log</summary>

```
{sync_log}
```

</details>
"""


class PRDefaults(BaseModel):
    title: str = "chore: sync {name} files"
    body_template: str = DEFAULT_BODY_TEMPLATE
    body_suffix: str = ""
    labels: list[str] = Field(default_factory=list)
    reviewers: list[str] = Field(default_factory=list)
    assignees: list[str] = Field(default_factory=list)

    def format_body(
        self,
        src_repo_url: str,
        src_sha: str,
        sync_log: str,
        dest_name: str,
    ) -> str:
        src_repo_name = src_repo_url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        body = self.body_template.format(
            src_repo_url=src_repo_url,
            src_repo_name=src_repo_name,
            src_sha=src_sha,
            src_sha_short=src_sha[:8],
            sync_log=sync_log,
            dest_name=dest_name,
        )
        if self.body_suffix:
            body = f"{body}\n---\n{self.body_suffix}"
        return body


class Destination(BaseModel):
    name: str
    repo_url: str = ""
    dest_path_relative: str
    copy_branch: str = ""
    default_branch: str = "main"
    skip_sections: dict[str, list[str]] = Field(default_factory=dict)

    def resolved_copy_branch(self, config_name: str) -> str:
        """Returns branch name, defaulting to sync/{config_name} if not set."""
        return self.copy_branch or f"sync/{config_name}"


class SrcConfig(BaseModel):
    CONFIG_EXT: ClassVar[str] = ".src.yaml"

    name: str
    git_remote: str = "origin"
    src_repo_url: str = ""
    schedule: str = "0 6 * * *"
    header_config: HeaderConfig = Field(default_factory=HeaderConfig)
    pr_defaults: PRDefaults = Field(default_factory=PRDefaults)
    paths: list[PathMapping] = Field(default_factory=list)
    destinations: list[Destination] = Field(default_factory=list)

    def find_destination(self, name: str) -> Destination:
        for dest in self.destinations:
            if dest.name == name:
                return dest
        raise ValueError(f"Destination not found: {name}")


def resolve_config_path(repo_root: Path, name: str) -> Path:
    return repo_root / ".github" / f"{name}{SrcConfig.CONFIG_EXT}"


def find_repo_root(start_path: Path) -> Path:
    current = start_path.resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    raise ValueError(f"No git repository found from {start_path}")
