from __future__ import annotations

import logging
from pathlib import Path

import typer

from path_sync import git_ops
from path_sync.models import find_repo_root
from path_sync.typer_app import app
from path_sync.validation import parse_skip_sections, validate_no_unauthorized_changes

logger = logging.getLogger(__name__)


@app.command("validate-no-changes")
def validate_no_changes(
    branch: str = typer.Option(
        "main", "-b", "--branch", help="Default branch to compare against"
    ),
    skip_sections_opt: str = typer.Option(
        "",
        "--skip-sections",
        help="Comma-separated path:section_id pairs to skip (e.g., 'justfile:coverage,pyproject.toml:default')",
    ),
) -> None:
    """Validate no unauthorized changes to synced files."""
    repo_root = find_repo_root(Path.cwd())
    repo = git_ops.get_repo(repo_root)

    current_branch = repo.active_branch.name
    if current_branch.startswith("sync/"):
        logger.info(f"On sync branch {current_branch}, validation skipped")
        return
    if current_branch == branch:
        logger.info(f"On default branch {branch}, validation skipped")
        return

    skip_sections = (
        parse_skip_sections(skip_sections_opt) if skip_sections_opt else None
    )
    unauthorized = validate_no_unauthorized_changes(repo_root, branch, skip_sections)

    if unauthorized:
        files_list = "\n  ".join(unauthorized)
        logger.error(
            f"Unauthorized changes in {len(unauthorized)} files:\n  {files_list}"
        )
        raise typer.Exit(1)

    logger.info("Validation passed: no unauthorized changes")
