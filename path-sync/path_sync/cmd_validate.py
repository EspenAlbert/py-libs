from __future__ import annotations

import logging
from pathlib import Path

import typer

from path_sync import git_ops
from path_sync.models import DestConfig, find_repo_root, resolve_config_path
from path_sync.typer_app import app
from path_sync.validation import validate_dest_config
from path_sync.yaml_utils import load_yaml_model

logger = logging.getLogger(__name__)


@app.command("validate-no-changes")
def validate_no_changes(
    name: str = typer.Option(..., "-n", "--name", help="Config name"),
) -> None:
    """Validate no unauthorized changes to synced files."""
    repo_root = find_repo_root(Path.cwd())
    config_path = resolve_config_path(repo_root, name, DestConfig)

    if not config_path.exists():
        logger.error(f"Dest config not found: {config_path}")
        raise typer.Exit(1)

    config = load_yaml_model(config_path, DestConfig)
    repo = git_ops.get_repo(repo_root)

    current_branch = repo.active_branch.name
    if current_branch.startswith("sync/"):
        logger.info(f"On sync branch {current_branch}, validation skipped")
        return

    unauthorized = validate_dest_config(repo_root, config)
    if unauthorized:
        files_list = "\n  ".join(unauthorized)
        logger.error(
            f"Unauthorized changes in {len(unauthorized)} files:\n  {files_list}"
        )
        raise typer.Exit(1)

    logger.info("Validation passed: no unauthorized changes")
