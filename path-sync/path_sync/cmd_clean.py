from __future__ import annotations

import logging
from pathlib import Path

import typer

from path_sync import header
from path_sync.models import DestConfig, find_repo_root
from path_sync.typer_app import app
from path_sync.yaml_utils import load_yaml_model

logger = logging.getLogger(__name__)


@app.command()
def clean(
    name: str = typer.Option("", "-n", "--name", help="Filter by config name"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without deleting"),
) -> None:
    """Remove orphaned synced files not in any dest config."""
    repo_root = find_repo_root(Path.cwd())

    dest_configs = _find_dest_configs(repo_root, name)
    # not necessary to have dest_configs to find orphaned files
    tracked_paths: set[Path] = set()
    for config in dest_configs:
        for mapping in config.always_paths:
            tracked_paths.update(mapping.expand_dest_paths(repo_root))

    orphaned = _find_orphaned_files(repo_root, tracked_paths)

    if not orphaned:
        logger.info("No orphaned files found")
        return

    for path in orphaned:
        if dry_run:
            logger.info(f"[DRY RUN] Would delete: {path}")
        else:
            path.unlink()
            logger.info(f"Deleted: {path}")


def _find_dest_configs(repo_root: Path, name_filter: str) -> list[DestConfig]:
    github_dir = repo_root / ".github"
    if not github_dir.exists():
        return []

    configs = []
    for config_file in github_dir.glob("*.dest.yaml"):
        if name_filter and not config_file.stem.startswith(name_filter):
            continue
        config = load_yaml_model(config_file, DestConfig)
        configs.append(config)

    return configs


def _find_orphaned_files(repo_root: Path, tracked: set[Path]) -> list[Path]:
    orphaned = []

    for ext in header.COMMENT_PREFIXES:
        glob_pattern = f"*{ext}"
        logger.info(
            f"Finding orphaned files with glob: {glob_pattern} from root: {repo_root}"
        )
        for path in repo_root.rglob(glob_pattern):
            if ".git" in path.parts:
                continue
            if path in tracked:
                continue
            if header.file_has_header(path):
                orphaned.append(path)

    return orphaned
