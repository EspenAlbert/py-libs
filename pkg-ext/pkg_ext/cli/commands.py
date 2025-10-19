"""CLI commands for pkg-ext."""

from pathlib import Path

import typer
from typer import Typer

from pkg_ext.cli.options import (
    option_bump_version,
    option_create_tag,
    option_git_changes_since,
    option_push,
)
from pkg_ext.cli.workflows import (
    GenerateApiInput,
    create_ctx,
    generate_api_workflow,
    post_merge_commit_workflow,
    sync_files,
)
from pkg_ext.config import load_project_config, load_user_config
from pkg_ext.git import GitSince, head_merge_pr
from pkg_ext.settings import PkgSettings, pkg_settings

app = Typer(name="pkg-ext", help="Generate public API for a package and more!")


def resolve_repo_root(cwd: Path) -> Path:
    """Find the repository root by looking for .git folder in cwd or parent directories."""
    for path in [cwd] + list(cwd.parents):
        if (path / ".git").exists():
            return path
    raise ValueError(f"Repository root not found starting from {cwd}")


def resolve_pkg_path_str(cwd: Path, repo_root: Path) -> str:
    """Find the package path by looking for __init__.py in cwd or checking if cwd is within a package."""
    # First, check if cwd itself is a package directory
    if (cwd / "__init__.py").exists():
        return str(cwd.relative_to(repo_root))

    # If not, look for any subdirectory with __init__.py
    for item in cwd.iterdir():
        if item.is_dir() and (item / "__init__.py").exists():
            return str(item.relative_to(repo_root))

    # If cwd is within a package, find the package root
    current = cwd
    while current != repo_root:
        if (current / "__init__.py").exists():
            return str(current.relative_to(repo_root))
        current = current.parent

    raise ValueError(f"No package directory found starting from {cwd}")


app = Typer(name="pkg-ext", help="Generate public API for a package and more!")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    pkg_path_str: str | None = typer.Option(
        None,
        "-p",
        "--path",
        "--pkg-path",
        help="Path to the package directory (auto-detected if not provided), expecting {pkg_path}/__init__.py to exist",
    ),
    repo_root: Path | None = typer.Option(
        None,
        help="Repository root directory (auto-detected from .git if not provided)",
    ),
    is_bot: bool = typer.Option(
        False,
        "--is-bot",
        envvar="PKG_EXT_IS_BOT",
        help="For CI to avoid any prompt hanging or accidental defaults made or to check for no more manual changes",
    ),
    skip_open: bool | None = typer.Option(
        None,
        "--skip-open",
        envvar="PKG_EXT_SKIP_OPEN",
        help="Skip opening files in editor. Uses user config or env var if not set explicitly.",
    ),
    tag_prefix: str | None = typer.Option(
        None,
        "--tag-prefix",
        envvar="PKG_EXT_TAG_PREFIX",
        help="{tag_prefix}{version} used in the git tag. Uses project config or env var if not set.",
    ),
):  # sourcery skip: raise-from-previous-error
    """pkg-ext: Generate public API for a package and more!"""
    if ctx.invoked_subcommand is None:
        # If no subcommand, show help
        typer.echo(ctx.get_help())
        raise typer.Exit()
    # Resolve repo_root with auto-detection
    if repo_root is None:
        try:
            resolved_repo_root = resolve_repo_root(Path.cwd())
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
    else:
        resolved_repo_root = repo_root

    # Auto-detect pkg_path if not provided
    if pkg_path_str is None:
        try:
            pkg_path_str = resolve_pkg_path_str(Path.cwd(), resolved_repo_root)
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    # Resolve global settings with proper precedence: CLI arg → Env var → Config file(user or proejct) → Default
    user_config = load_user_config()
    project_config = load_project_config(resolved_repo_root)

    # Create PkgSettings once in the callback
    settings = pkg_settings(
        repo_root=resolved_repo_root,
        is_bot=is_bot,
        pkg_path=pkg_path_str,
        skip_open_in_editor=skip_open
        if skip_open is not None
        else user_config.skip_open_in_editor,
        tag_prefix=tag_prefix if tag_prefix is not None else project_config.tag_prefix,
    )
    # Store settings for use by subcommands
    ctx.obj = settings


@app.command()
def pre_push(
    ctx: typer.Context,
    git_changes_since: GitSince = option_git_changes_since,
):
    """Use this to run before a push. Will ask questions about your changes to ensure the changelog and release can be updated later"""
    settings: PkgSettings = ctx.obj
    settings.dev_mode = True

    api_input = GenerateApiInput(
        settings=settings,
        git_changes_since=git_changes_since,
        bump_version=False,
        create_tag=False,
        push=False,
    )
    generate_api_workflow(api_input)


@app.command()
def pre_merge(
    ctx: typer.Context,
    git_changes_since: GitSince = option_git_changes_since,
):
    """Use this as a CI check. No merge until this passes. Ensures no manual changes are missing."""
    settings: PkgSettings = ctx.obj
    settings.force_bot()
    settings.dev_mode = True

    api_input = GenerateApiInput(
        settings=settings,
        git_changes_since=git_changes_since,
        bump_version=False,
        create_tag=False,
        push=False,
    )
    generate_api_workflow(api_input)


@app.command()
def post_merge(
    ctx: typer.Context,
    explicit_pr: int = typer.Option(
        0, help="Use this if the HEAD commit is not a merge"
    ),
    push: bool = option_push,
):
    """Use this after a merge to bump version, creates the automated release files"""

    settings: PkgSettings = ctx.obj
    settings.force_bot()
    # Use local tag_prefix override if provided, otherwise use global

    pr = explicit_pr or head_merge_pr(Path(settings.repo_root))
    api_input = GenerateApiInput(
        settings=settings,
        git_changes_since=GitSince.NO_GIT_CHANGES,  # will not add new entries
        bump_version=True,
        create_tag=True,
        push=push,
    )
    pkg_ctx = create_ctx(api_input)
    sync_files(api_input, pkg_ctx)
    post_merge_commit_workflow(
        repo_path=settings.repo_root,
        changelog_dir_path=pkg_ctx.settings.changelog_path,
        pr_number=pr,
        tag_prefix=settings.tag_prefix,
        new_version=str(pkg_ctx.run_state.new_version),
        push=push,
    )


@app.command()
def generate_api(
    ctx: typer.Context,
    git_changes_since: GitSince = option_git_changes_since,
    bump_version: bool = option_bump_version,
    create_tag: bool = option_create_tag,
    push: bool = option_push,
    explicit_pr: int = typer.Option(
        0, "--pr", help="Use this if the HEAD commit is not a merge"
    ),
):
    """Generate API documentation and manage package releases."""
    settings: PkgSettings = ctx.obj
    # Use command-specific overrides if provided, otherwise use global settings
    api_input = GenerateApiInput(
        settings=settings,
        git_changes_since=git_changes_since,
        bump_version=bump_version,
        create_tag=create_tag,
        push=push,
    )
    if pkg_ctx := generate_api_workflow(api_input):
        if api_input.create_tag:
            post_merge_commit_workflow(
                repo_path=settings.repo_root,
                changelog_dir_path=pkg_ctx.settings.changelog_path,
                pr_number=explicit_pr or pkg_ctx.git_changes.current_pr,
                tag_prefix=settings.tag_prefix,
                new_version=str(pkg_ctx.run_state.new_version),
                push=push,
            )
