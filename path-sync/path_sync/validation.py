from __future__ import annotations

import logging
from pathlib import Path

from path_sync import git_ops, header

logger = logging.getLogger(__name__)


def validate_no_unauthorized_changes(
    repo_root: Path,
    default_branch: str = "main",
) -> list[str]:
    """Find files with path-sync header that have unauthorized git changes."""
    repo = git_ops.get_repo(repo_root)
    base_ref = f"origin/{default_branch}"
    unauthorized: list[str] = []

    for path in git_ops.get_changed_files(repo, base_ref):
        if not path.exists():
            continue
        if not header.file_has_header(path):
            continue
        rel_path = str(path.relative_to(repo_root))
        unauthorized.append(rel_path)

    return sorted(unauthorized)
