from __future__ import annotations

import glob
import logging
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import typer

from path_sync import git_ops, header, sections, workflow_gen
from path_sync.file_utils import ensure_parents_write_text
from path_sync.models import (
    LOG_FORMAT,
    Destination,
    PathMapping,
    SrcConfig,
    find_repo_root,
    resolve_config_path,
)
from path_sync.typer_app import app
from path_sync.yaml_utils import load_yaml_model

logger = logging.getLogger(__name__)

EXIT_NO_CHANGES = 0
EXIT_CHANGES = 1
EXIT_ERROR = 2


@dataclass
class SyncResult:
    content_changes: int = 0
    tools_changes: int = 0
    orphans_deleted: int = 0
    synced_paths: set[Path] = field(default_factory=set)

    @property
    def total(self) -> int:
        return self.content_changes + self.tools_changes + self.orphans_deleted


@contextmanager
def capture_sync_log(dest_name: str):
    with tempfile.TemporaryDirectory(prefix="path-sync-") as tmpdir:
        log_path = Path(tmpdir) / f"{dest_name}.log"
        file_handler = logging.FileHandler(log_path, mode="w")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root_logger = logging.getLogger("path_sync")
        root_logger.addHandler(file_handler)
        try:
            yield log_path
        finally:
            file_handler.close()
            root_logger.removeHandler(file_handler)


@dataclass
class CopyOptions:
    dry_run: bool = False
    force_overwrite: bool = False
    skip_checkout: bool = False
    checkout_from_default: bool = False
    force_push: bool = True
    force_tools_pr: bool = False
    no_commit: bool = False
    no_push: bool = False
    no_pr: bool = False
    pr_title: str = ""
    pr_labels: str = ""
    pr_reviewers: str = ""
    pr_assignees: str = ""


@app.command()
def copy(
    name: str = typer.Option(..., "-n", "--name", help="Config name"),
    dest_filter: str = typer.Option(
        "", "-d", "--dest", help="Filter destinations (comma-separated)"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing"),
    force_overwrite: bool = typer.Option(
        False,
        "--force-no-header-updates",
        help="Overwrite files even if header removed",
    ),
    detailed_exit_code: bool = typer.Option(False, "--detailed-exit-code"),
    skip_dest_checkout: bool = typer.Option(False, "--skip-dest-checkout"),
    checkout_from_default: bool = typer.Option(
        False,
        "--checkout-from-default",
        help="Reset to origin/default before sync (for CI)",
    ),
    force_push: bool = typer.Option(True, "--force-push/--no-force-push"),
    force_tools_pr: bool = typer.Option(
        False, "--force-tools-pr", help="Create PR even if only tools changed"
    ),
    no_commit: bool = typer.Option(False, "--no-commit"),
    no_push: bool = typer.Option(False, "--no-push"),
    no_pr: bool = typer.Option(False, "--no-pr"),
    pr_title: str = typer.Option("", "--pr-title"),
    pr_labels: str = typer.Option("", "--pr-labels"),
    pr_reviewers: str = typer.Option("", "--pr-reviewers"),
    pr_assignees: str = typer.Option("", "--pr-assignees"),
) -> None:
    """Copy files from SRC to DEST repositories."""
    src_root = find_repo_root(Path.cwd())
    config_path = resolve_config_path(src_root, name)

    if not config_path.exists():
        logger.error(f"Config not found: {config_path}")
        raise typer.Exit(EXIT_ERROR if detailed_exit_code else 1)

    config = load_yaml_model(config_path, SrcConfig)
    src_repo = git_ops.get_repo(src_root)
    current_sha = git_ops.get_current_sha(src_repo)
    src_repo_url = git_ops.get_remote_url(src_repo, config.git_remote)

    opts = CopyOptions(
        dry_run=dry_run,
        force_overwrite=force_overwrite,
        skip_checkout=skip_dest_checkout,
        checkout_from_default=checkout_from_default,
        force_push=force_push,
        force_tools_pr=force_tools_pr,
        no_commit=no_commit,
        no_push=no_push,
        no_pr=no_pr,
        pr_title=pr_title or config.pr_defaults.title,
        pr_labels=pr_labels or ",".join(config.pr_defaults.labels),
        pr_reviewers=pr_reviewers or ",".join(config.pr_defaults.reviewers),
        pr_assignees=pr_assignees or ",".join(config.pr_defaults.assignees),
    )

    destinations = config.destinations
    if dest_filter:
        filter_names = [n.strip() for n in dest_filter.split(",")]
        destinations = [d for d in destinations if d.name in filter_names]

    total_changes = 0
    for dest in destinations:
        try:
            with capture_sync_log(dest.name) as log_path:
                changes = _sync_destination(
                    config, dest, src_root, current_sha, src_repo_url, opts, log_path
                )
            total_changes += changes
        except Exception as e:
            logger.error(f"Failed to sync {dest.name}: {e}")
            if detailed_exit_code:
                raise typer.Exit(EXIT_ERROR)
            raise

    if detailed_exit_code:
        raise typer.Exit(EXIT_CHANGES if total_changes > 0 else EXIT_NO_CHANGES)


def _sync_destination(
    config: SrcConfig,
    dest: Destination,
    src_root: Path,
    current_sha: str,
    src_repo_url: str,
    opts: CopyOptions,
    log_path: Path,
) -> int:
    dest_root = (src_root / dest.dest_path_relative).resolve()
    dest_repo = _ensure_dest_repo(dest, dest_root)

    if not opts.skip_checkout and not opts.dry_run:
        git_ops.prepare_copy_branch(
            repo=dest_repo,
            default_branch=dest.default_branch,
            copy_branch=dest.copy_branch,
            from_default=opts.checkout_from_default,
        )

    result = _sync_paths(config, dest, src_root, dest_root, opts)

    if result.total == 0:
        logger.info(f"{dest.name}: No changes")
        return 0
    logger.info(f"{dest.name}: Found {result.total} changes")
    if (
        result.content_changes == 0
        and result.orphans_deleted == 0
        and not opts.force_tools_pr
    ):
        logger.info(f"{dest.name}: Tools-only changes, skipping PR")
        return 0

    if opts.dry_run:
        logger.info(f"{dest.name}: Would make {result.total} changes")
        return result.total

    return _commit_and_pr(
        config, dest_repo, dest_root, dest, current_sha, src_repo_url, opts, log_path
    )


def _ensure_dest_repo(dest: Destination, dest_root: Path):
    if not dest_root.exists():
        if not dest.repo_url:
            raise ValueError(f"Dest {dest.name} not found and no repo_url configured")
        git_ops.clone_repo(dest.repo_url, dest_root)
    return git_ops.get_repo(dest_root)


def _sync_paths(
    config: SrcConfig,
    dest: Destination,
    src_root: Path,
    dest_root: Path,
    opts: CopyOptions,
) -> SyncResult:
    result = SyncResult()
    for mapping in config.paths:
        changes, paths = _sync_path(
            mapping,
            src_root,
            dest_root,
            dest,
            config.name,
            opts.dry_run,
            opts.force_overwrite,
        )
        result.content_changes += changes
        result.synced_paths.update(paths)

    result.tools_changes = _sync_tools_update(config, dest, dest_root, opts)
    result.orphans_deleted = _cleanup_orphans(
        dest_root, config.name, result.synced_paths, opts.dry_run
    )
    return result


def _sync_path(
    mapping: PathMapping,
    src_root: Path,
    dest_root: Path,
    dest: Destination,
    config_name: str,
    dry_run: bool,
    force_overwrite: bool,
) -> tuple[int, set[Path]]:
    src_pattern = src_root / mapping.src_path
    changes = 0
    synced: set[Path] = set()

    if "*" in mapping.src_path:
        glob_prefix = mapping.src_path.split("*")[0].rstrip("/")
        dest_base = mapping.dest_path or glob_prefix
        matches = glob.glob(str(src_pattern), recursive=True)
        if not matches:
            logger.warning(f"Glob matched no files: {mapping.src_path}")
        for src_file in matches:
            src_path = Path(src_file)
            if src_path.is_file():
                rel = src_path.relative_to(src_root / glob_prefix)
                dest_path = dest_root / dest_base / rel
                dest_key = str(Path(dest_base) / rel)
                changes += _copy_with_header(
                    src_path,
                    dest_path,
                    dest,
                    dest_key,
                    config_name,
                    dry_run,
                    force_overwrite,
                )
                synced.add(dest_path)
    elif src_pattern.is_dir():
        dest_base = mapping.resolved_dest_path()
        for src_file in src_pattern.rglob("*"):
            if src_file.is_file():
                rel = src_file.relative_to(src_pattern)
                dest_path = dest_root / dest_base / rel
                dest_key = str(Path(dest_base) / rel)
                changes += _copy_with_header(
                    src_file,
                    dest_path,
                    dest,
                    dest_key,
                    config_name,
                    dry_run,
                    force_overwrite,
                )
                synced.add(dest_path)
    elif src_pattern.is_file():
        dest_base = mapping.resolved_dest_path()
        dest_path = dest_root / dest_base
        changes += _copy_with_header(
            src_pattern,
            dest_path,
            dest,
            dest_base,
            config_name,
            dry_run,
            force_overwrite,
        )
        synced.add(dest_path)
    else:
        logger.warning(f"Source not found: {mapping.src_path}")

    return changes, synced


def _copy_with_header(
    src: Path,
    dest_path: Path,
    dest: Destination,
    dest_key: str,
    config_name: str,
    dry_run: bool,
    force_overwrite: bool = False,
) -> int:
    src_content = src.read_text()
    skip_list = dest.skip_sections.get(dest_key, [])

    if sections.has_sections(src_content):
        return _copy_with_sections(
            src_content, dest_path, skip_list, config_name, dry_run, force_overwrite
        )

    # No sections: full-file replacement
    if dest_path.exists():
        existing = dest_path.read_text()
        if not header.has_header(existing) and not force_overwrite:
            logger.info(f"Skipping {dest_path} (header removed - opted out)")
            return 0
        if header.remove_header(existing) == src_content:
            return 0

    new_content = header.add_header(src_content, dest_path.suffix, config_name)
    if dry_run:
        logger.info(f"[DRY RUN] Would write: {dest_path}")
        return 1

    ensure_parents_write_text(dest_path, new_content)
    logger.info(f"Wrote: {dest_path}")
    return 1


def _copy_with_sections(
    src_content: str,
    dest_path: Path,
    skip_list: list[str],
    config_name: str,
    dry_run: bool,
    force_overwrite: bool,
) -> int:
    src_sections = sections.extract_sections(src_content)

    if dest_path.exists():
        existing = dest_path.read_text()
        if not header.has_header(existing) and not force_overwrite:
            logger.info(f"Skipping {dest_path} (header removed - opted out)")
            return 0
        dest_body = header.remove_header(existing)
        new_body = sections.replace_sections(dest_body, src_sections, skip_list)
    else:
        new_body = src_content

    new_content = header.add_header(new_body, dest_path.suffix, config_name)

    if dest_path.exists():
        if dest_path.read_text() == new_content:
            return 0

    if dry_run:
        logger.info(f"[DRY RUN] Would write: {dest_path}")
        return 1

    ensure_parents_write_text(dest_path, new_content)
    logger.info(f"Wrote: {dest_path}")
    return 1


def _cleanup_orphans(
    dest_root: Path,
    config_name: str,
    synced_paths: set[Path],
    dry_run: bool,
) -> int:
    deleted = 0
    for path in _find_files_with_config(dest_root, config_name):
        if path not in synced_paths:
            if dry_run:
                logger.info(f"[DRY RUN] Would delete orphan: {path}")
            else:
                path.unlink()
                logger.info(f"Deleted orphan: {path}")
            deleted += 1
    return deleted


def _find_files_with_config(dest_root: Path, config_name: str) -> list[Path]:
    result = []
    for ext in header.COMMENT_PREFIXES:
        for path in dest_root.rglob(f"*{ext}"):
            if ".git" in path.parts:
                continue
            if header.file_get_config_name(path) == config_name:
                result.append(path)
    return result


def _sync_tools_update(
    config: SrcConfig,
    dest: Destination,
    dest_root: Path,
    opts: CopyOptions,
) -> int:
    changes = 0

    if dest.tools_update.github_workflows:
        wf_path = dest_root / workflow_gen.validate_workflow_path(config.name)
        if not wf_path.exists():
            content = workflow_gen.generate_validate_workflow(
                name=config.name,
                copy_branch=dest.copy_branch,
                default_branch=dest.default_branch,
            )
            if opts.dry_run:
                logger.info(f"[DRY RUN] Would write workflow: {wf_path}")
            else:
                ensure_parents_write_text(wf_path, content)
                logger.info(f"Wrote workflow: {wf_path}")
            changes += 1

    if dest.tools_update.justfile:
        changes += _sync_justfile_recipe(config.name, dest_root, opts)

    if dest.tools_update.path_sync_wheel:
        _sync_wheel(dest_root, opts)

    return changes


def _sync_justfile_recipe(name: str, dest_root: Path, opts: CopyOptions) -> int:
    justfile_path = dest_root / "justfile"
    changed = workflow_gen.update_justfile(
        justfile_path, name, workflow_gen.JustfileRecipeKind.VALIDATE, opts.dry_run
    )
    return 1 if changed else 0


def _sync_wheel(dest_root: Path, opts: CopyOptions) -> None:
    pkg_root = Path(__file__).parent.parent
    wheel = _build_wheel(pkg_root, opts.dry_run)
    if not wheel:
        return

    dest_dir = dest_root / ".github"
    dest_wheel = dest_dir / wheel.name

    for old_wheel in dest_dir.glob("path_sync-*.whl"):
        if old_wheel != dest_wheel:
            if opts.dry_run:
                logger.info(f"[DRY RUN] Would remove old wheel: {old_wheel}")
            else:
                old_wheel.unlink()
                logger.info(f"Removed old wheel: {old_wheel}")

    if opts.dry_run:
        logger.info(f"[DRY RUN] Would copy wheel: {dest_wheel}")
        return

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_wheel.write_bytes(wheel.read_bytes())
    logger.info(f"Copied wheel: {dest_wheel}")


def _build_wheel(pkg_root: Path, dry_run: bool) -> Path | None:
    dist_dir = pkg_root / "dist"

    if dry_run:
        logger.info("[DRY RUN] Would build wheel")
        wheels = sorted(dist_dir.glob("path_sync-*.whl")) if dist_dir.exists() else []
        return wheels[-1] if wheels else None

    if dist_dir.exists():
        for old in dist_dir.glob("path_sync-*.whl"):
            old.unlink()

    logger.info("Building wheel...")
    result = subprocess.run(
        ["uv", "build", "--wheel"],
        cwd=pkg_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error(f"Failed to build wheel: {result.stderr}")
        raise RuntimeError("Wheel build failed")

    wheels = sorted(dist_dir.glob("path_sync-*.whl"))
    assert len(wheels) == 1, f"Expected 1 wheel, got {len(wheels)}"
    return wheels[0]


def _commit_and_pr(
    config: SrcConfig,
    repo,
    dest_root: Path,
    dest: Destination,
    sha: str,
    src_repo_url: str,
    opts: CopyOptions,
    log_path: Path,
) -> int:
    if opts.no_commit:
        return 1

    git_ops.commit_changes(repo, f"chore: sync {config.name} from {sha[:8]}")

    if opts.no_push:
        return 1

    git_ops.push_branch(repo, dest.copy_branch, force=opts.force_push)

    if opts.no_pr:
        return 1

    sync_log = log_path.read_text() if log_path.exists() else ""
    pr_body = config.pr_defaults.format_body(
        src_repo_url=src_repo_url,
        src_sha=sha,
        sync_log=sync_log,
        dest_name=dest.name,
    )

    title = opts.pr_title.format(name=config.name, dest_name=dest.name)
    git_ops.create_or_update_pr(
        dest_root,
        dest.copy_branch,
        title,
        pr_body,
        opts.pr_labels.split(",") if opts.pr_labels else None,
        opts.pr_reviewers.split(",") if opts.pr_reviewers else None,
        opts.pr_assignees.split(",") if opts.pr_assignees else None,
    )
    return 1
