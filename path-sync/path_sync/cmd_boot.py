from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from path_sync import git_ops, workflow_gen
from path_sync.file_utils import ensure_parents_write_text
from path_sync.models import (
    Destination,
    PathMapping,
    SrcConfig,
    find_repo_root,
    resolve_config_path,
)
from path_sync.typer_app import app
from path_sync.yaml_utils import dump_yaml_model, load_yaml_model

logger = logging.getLogger(__name__)


@app.command()
def boot(
    name: str = typer.Option(..., "-n", "--name", help="Config name"),
    dest_paths: Annotated[
        list[str], typer.Option("-d", "--dest", help="Destination relative paths")
    ] = [],
    always_paths: Annotated[
        list[str], typer.Option("-p", "--path", help="Always paths (glob patterns)")
    ] = [],
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing"),
    regen: bool = typer.Option(False, "--regen", help="Regenerate all files"),
) -> None:
    """Initialize or update SRC repo tooling."""
    repo_root = find_repo_root(Path.cwd())
    config_path = resolve_config_path(repo_root, name, SrcConfig)

    if config_path.exists() and not regen:
        config = load_yaml_model(config_path, SrcConfig)
        logger.info(f"Using existing config: {config_path}")
    else:
        src_repo = git_ops.get_repo(repo_root)
        src_repo_url = git_ops.get_remote_url(src_repo, "origin")

        destinations = _build_destinations(repo_root, dest_paths)
        path_mappings = [PathMapping(src_path=p) for p in always_paths]

        config = SrcConfig(
            name=name,
            src_repo_url=src_repo_url,
            always_paths=path_mappings,
            destinations=destinations,
        )
        config_content = dump_yaml_model(config)
        _write_file(config_path, config_content, dry_run, "config")

    if config.src_tools_update.github_workflows:
        workflow_path = repo_root / workflow_gen.copy_workflow_path(name)
        if not workflow_path.exists() or regen:
            content = workflow_gen.generate_copy_workflow(config)
            _write_file(workflow_path, content, dry_run, "workflow")

    if config.src_tools_update.justfile:
        _update_justfile(repo_root, name, dry_run)

    if dry_run:
        logger.info("Dry run complete - no files written")
    else:
        logger.info("Boot complete")


def _build_destinations(repo_root: Path, dest_paths: list[str]) -> list[Destination]:
    destinations = []
    for rel_path in dest_paths:
        dest_dir = (repo_root / rel_path).resolve()
        dest_name = dest_dir.name

        dest = Destination(name=dest_name, dest_path_relative=rel_path)

        if git_ops.is_git_repo(dest_dir):
            dest_repo = git_ops.get_repo(dest_dir)
            dest.repo_url = git_ops.get_remote_url(dest_repo, "origin")
            dest.default_branch = git_ops.get_default_branch(dest_repo)
            logger.info(f"Found git repo at {dest_dir}: {dest.repo_url}")

        destinations.append(dest)

    return destinations


def _write_file(path: Path, content: str, dry_run: bool, desc: str) -> None:
    if dry_run:
        logger.info(f"[DRY RUN] Would write {desc}: {path}")
        return
    ensure_parents_write_text(path, content)
    logger.info(f"Wrote {desc}: {path}")


def _update_justfile(repo_root: Path, name: str, dry_run: bool) -> None:
    justfile_path = repo_root / "justfile"
    workflow_gen.update_justfile(
        justfile_path, name, workflow_gen.JustfileRecipeKind.COPY, dry_run
    )
