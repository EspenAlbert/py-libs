"""CLI commands for pkg-ext."""

from pathlib import Path

import typer
from typer import Typer

from pkg_ext.cli.options import (
    argument_pkg_path,
    option_bump_version,
    option_create_tag,
    option_dev_mode,
    option_git_changes_since,
    option_is_bot,
    option_push,
    option_tag_prefix,
)
from pkg_ext.cli.workflows import (
    GenerateApiInput,
    generate_api_workflow,
    post_merge_commit_workflow,
)
from pkg_ext.config import load_project_config, load_user_config
from pkg_ext.git import GitSince, head_merge_pr

app = Typer(name="pkg-ext", help="Generate public API for a package and more!")


def resolve_skip_open_in_editor(cli_value: bool | None) -> bool:
    """Resolve skip_open_in_editor with fallback to user config."""
    if cli_value is not None:
        return cli_value
    return load_user_config().skip_open_in_editor


def resolve_tag_prefix(cli_value: str | None, repo_root: Path) -> str:
    """Resolve tag_prefix with fallback to project config."""
    if cli_value is not None:
        return cli_value
    return load_project_config(repo_root).tag_prefix


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
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
    repo_root: Path = typer.Option(
        default_factory=Path.cwd,
        help="Repository root directory",
    ),
):
    """pkg-ext: Generate public API for a package and more!"""
    if ctx.invoked_subcommand is None:
        # If no subcommand, show help
        typer.echo(ctx.get_help())
        raise typer.Exit()

    # Store global configuration in context for use by subcommands
    ctx.ensure_object(dict)

    # Resolve global settings with fallbacks
    ctx.obj["skip_open_in_editor"] = resolve_skip_open_in_editor(skip_open)
    ctx.obj["tag_prefix"] = resolve_tag_prefix(tag_prefix, repo_root)
    ctx.obj["repo_root"] = repo_root


@app.command()
def pre_push(
    ctx: typer.Context,
    pkg_path_str: str = argument_pkg_path,
    git_changes_since: GitSince = option_git_changes_since,
):
    """Use this to run before a push. Will ask questions about your changes to ensure the changelog and release can be updated later"""
    api_input = GenerateApiInput(
        pkg_path_str=pkg_path_str,
        repo_root=ctx.obj["repo_root"],
        skip_open_in_editor=ctx.obj["skip_open_in_editor"],
        dev_mode=True,
        git_changes_since=git_changes_since,
        bump_version=False,
        is_bot=False,
        create_tag=False,
        tag_prefix=ctx.obj["tag_prefix"],
        push=False,
    )
    generate_api_workflow(api_input)


@app.command()
def pre_merge(
    ctx: typer.Context,
    pkg_path_str: str = argument_pkg_path,
    git_changes_since: GitSince = option_git_changes_since,
):
    """Use this as a CI check. No merge until this passes. Ensures no manual changes are missing."""
    api_input = GenerateApiInput(
        pkg_path_str=pkg_path_str,
        repo_root=ctx.obj["repo_root"],
        skip_open_in_editor=True,  # Always skip in CI
        dev_mode=True,
        git_changes_since=git_changes_since,
        bump_version=False,
        is_bot=True,
        create_tag=False,
        tag_prefix=ctx.obj["tag_prefix"],
        push=False,
    )
    generate_api_workflow(api_input)


@app.command()
def post_merge(
    ctx: typer.Context,
    pkg_path_str: str = argument_pkg_path,
    tag_prefix: str | None = option_tag_prefix,
    explicit_pr: int = typer.Option(
        0, help="Use this if the HEAD commit is not a merge"
    ),
    push: bool = option_push,
):
    """Use this after a merge to bump version, creates the automated release files."""
    from pkg_ext.cli.workflows import create_ctx, sync_files

    repo_root = ctx.obj["repo_root"]
    # Use local tag_prefix override if provided, otherwise use global
    final_tag_prefix = tag_prefix if tag_prefix is not None else ctx.obj["tag_prefix"]

    pr = explicit_pr or head_merge_pr(Path(repo_root))
    api_input = GenerateApiInput(
        pkg_path_str=pkg_path_str,
        repo_root=repo_root,
        skip_open_in_editor=True,
        dev_mode=False,
        tag_prefix=final_tag_prefix,
        git_changes_since=GitSince.NO_GIT_CHANGES,  # will not add new entries
        is_bot=True,
        bump_version=True,
        create_tag=True,
        push=push,
    )
    pkg_ctx = create_ctx(api_input)
    sync_files(api_input, pkg_ctx)
    post_merge_commit_workflow(
        repo_path=repo_root,
        changelog_dir_path=pkg_ctx.settings.changelog_path,
        pr_number=pr,
        tag_prefix=final_tag_prefix,
        new_version=str(pkg_ctx.run_state.new_version),
        push=push,
    )


@app.command()
def generate_api(
    ctx: typer.Context,
    pkg_path_str: str = argument_pkg_path,
    repo_root: Path | None = typer.Option(
        None, "--repo-root", help="Repository root directory (overrides global setting)"
    ),
    skip_open_in_editor: bool | None = typer.Option(
        None, "--skip-open", help="Override global skip-open setting"
    ),
    dev_mode: bool = option_dev_mode,
    git_changes_since: GitSince = option_git_changes_since,
    bump_version: bool = option_bump_version,
    is_bot: bool = option_is_bot,
    create_tag: bool = option_create_tag,
    tag_prefix: str = typer.Option(
        None, "--tag-prefix", help="Override global tag-prefix setting"
    ),
    push: bool = option_push,
    explicit_pr: int = typer.Option(
        0, "--pr", help="Use this if the HEAD commit is not a merge"
    ),
):
    """Generate API documentation and manage package releases."""
    # Use command-specific repo_root if provided, otherwise use global setting
    final_repo_root = repo_root if repo_root is not None else ctx.obj["repo_root"]

    # Use command-specific overrides if provided, otherwise use global settings
    final_skip_open = (
        skip_open_in_editor
        if skip_open_in_editor is not None
        else ctx.obj["skip_open_in_editor"]
    )
    final_tag_prefix = tag_prefix if tag_prefix is not None else ctx.obj["tag_prefix"]

    api_input = GenerateApiInput(
        pkg_path_str=pkg_path_str,
        repo_root=final_repo_root,
        skip_open_in_editor=final_skip_open,
        dev_mode=dev_mode,
        git_changes_since=git_changes_since,
        bump_version=bump_version,
        is_bot=is_bot,
        create_tag=create_tag,
        tag_prefix=final_tag_prefix,
        push=push,
    )
    if pkg_ctx := generate_api_workflow(api_input):
        if api_input.create_tag:
            post_merge_commit_workflow(
                repo_path=final_repo_root,
                changelog_dir_path=pkg_ctx.settings.changelog_path,
                pr_number=explicit_pr or pkg_ctx.git_changes.current_pr,
                tag_prefix=final_tag_prefix,
                new_version=str(pkg_ctx.run_state.new_version),
                push=push,
            )
