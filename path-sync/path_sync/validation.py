from __future__ import annotations

import logging
from pathlib import Path

from path_sync import git_ops, header
from path_sync.models import DestConfig

logger = logging.getLogger(__name__)


def validate_dest_config(repo_root: Path, config: DestConfig) -> list[str]:
    """Return sorted list of relative paths with unauthorized changes."""
    repo = git_ops.get_repo(repo_root)
    base_ref = f"origin/{config.default_branch}"
    unauthorized: list[str] = []

    for mapping in config.always_paths:
        for dest_path in mapping.expand_dest_paths(repo_root):
            if not header.file_has_header(dest_path):
                logger.info(f"{dest_path.name}: opted out")
                continue

            rel_path = str(dest_path.relative_to(repo_root))
            if git_ops.file_has_git_changes(repo, dest_path, base_ref):
                unauthorized.append(rel_path)
            else:
                logger.info(f"{rel_path}: ok")

    return sorted(unauthorized)
