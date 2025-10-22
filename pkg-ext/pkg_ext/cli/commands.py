"""CLI commands for pkg-ext."""

import logging
from pathlib import Path

import typer
from typer import Typer
from zero_3rdparty.file_utils import ensure_parents_write_text

from pkg_ext.changelog.actions import (
    ChangelogAction,
    ChangelogActionType,
    ReleaseChangelog,
    parse_changelog_actions,
)
from pkg_ext.changelog.write_changelog_md import read_changelog_section
from pkg_ext.cli.options import (
    option_bump_version,
    option_create_tag,
    option_git_changes_since,
    option_pr,
    option_push,
)
from pkg_ext.cli.workflows import (
    GenerateApiInput,
    clean_old_entries,
    create_ctx,
    generate_api_workflow,
    post_merge_commit_workflow,
    sync_files,
)
from pkg_ext.git_usage import GitSince, head_merge_pr
from pkg_ext.settings import PkgSettings, pkg_settings

logger = logging.getLogger(__name__)
app = Typer(name="pkg-ext", help="Generate public API for a package and more!")


def resolve_repo_root(cwd: Path) -> Path:
    """Find the repository root by looking for .git folder in cwd or parent directories."""
    for path in [cwd] + list(cwd.parents):
        if (path / ".git").exists():
            return path
    raise ValueError(f"Repository root not found starting from {cwd}")


def is_package_dir(path: Path) -> bool:
    return path.is_dir() and (path / "__init__.py").exists()


def resolve_pkg_path_str(cwd: Path, repo_root: Path) -> str:
    """Find the package path by looking for __init__.py in cwd or checking if cwd is within a package."""
    # First, check if cwd itself is a package directory
    if is_package_dir(cwd):
        return str(cwd.relative_to(repo_root))

    # If not, look for any subdirectory with __init__.py
    for item in cwd.iterdir():
        if is_package_dir(item):
            return str(item.relative_to(repo_root))

    # If cwd is within a package, find the package root
    current = cwd
    for parent in cwd.parents:
        if parent == repo_root:
            break
        if is_package_dir(parent):
            return str(current.relative_to(repo_root))
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
        help="Path to the package directory (auto-detected if not provided), expecting {pkg_path}/**/__init__.py to exist",
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
    if pkg_path_str is not None:
        candidate = resolved_repo_root / pkg_path_str
        if not is_package_dir(candidate):
            pkg_path_str = resolve_pkg_path_str(candidate, resolved_repo_root)

    if pkg_path_str is None:
        pkg_path_str = resolve_pkg_path_str(Path.cwd(), resolved_repo_root)

    ctx.obj = pkg_settings(
        repo_root=resolved_repo_root,
        is_bot=is_bot,
        pkg_path=pkg_path_str,
        skip_open_in_editor=skip_open,
        tag_prefix=tag_prefix,
    )


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
    explicit_pr: int = option_pr,
    push: bool = option_push,
    skip_clean_old_entries: bool = typer.Option(
        False,
        "--skip-clean",
    ),
):
    """Use this after a merge to bump version, creates the automated release files"""
    settings: PkgSettings = ctx.obj
    settings.force_bot()
    pr = explicit_pr or head_merge_pr(Path(settings.repo_root))
    logger.info(f"pr found: {pr}")
    api_input = GenerateApiInput(
        settings=settings,
        git_changes_since=GitSince.NO_GIT_CHANGES,  # will not add new entries
        bump_version=True,
        create_tag=True,
        push=push,
        explicit_pr=pr,
    )
    pkg_ctx = create_ctx(api_input)
    sync_files(api_input, pkg_ctx)
    post_merge_commit_workflow(
        repo_path=settings.repo_root,
        changelog_dir_path=pkg_ctx.settings.changelog_dir,
        pr_number=pr,
        tag_prefix=settings.tag_prefix,
        old_version=pkg_ctx.run_state.old_version,
        new_version=pkg_ctx.run_state.new_version,
        push=push,
    )
    if not skip_clean_old_entries:
        clean_old_entries(settings)


@app.command()
def generate_api(
    ctx: typer.Context,
    git_changes_since: GitSince = option_git_changes_since,
    bump_version: bool = option_bump_version,
    create_tag: bool = option_create_tag,
    push: bool = option_push,
    explicit_pr: int = option_pr,
):
    """Generate API documentation and manage package releases."""
    settings: PkgSettings = ctx.obj
    api_input = GenerateApiInput(
        settings=settings,
        git_changes_since=git_changes_since,
        bump_version=bump_version,
        create_tag=create_tag,
        push=push,
        explicit_pr=explicit_pr,
    )
    if pkg_ctx := generate_api_workflow(api_input):
        if api_input.create_tag:
            post_merge_commit_workflow(
                repo_path=settings.repo_root,
                changelog_dir_path=pkg_ctx.settings.changelog_dir,
                pr_number=explicit_pr or pkg_ctx.git_changes.current_pr,
                tag_prefix=settings.tag_prefix,
                old_version=pkg_ctx.run_state.old_version,
                new_version=pkg_ctx.run_state.new_version,
                push=push,
            )


def find_release_action(
    changelog_dir: Path, version: str
) -> ChangelogAction[ReleaseChangelog]:
    for changelog_action in parse_changelog_actions(changelog_dir):
        if (
            changelog_action.type == ChangelogActionType.RELEASE
            and changelog_action.name == version
        ):
            pr = changelog_action.pr
            assert pr, f"found changelog action: {changelog_action} but pr missing"
            return changelog_action
    raise ValueError(f"couldn't find a release for {version}")


@app.command()
def release_notes(
    ctx: typer.Context,
    tag_name: str = typer.Option(..., "--tag", help="tag to find release notes for"),
):
    settings: PkgSettings = ctx.obj
    version = tag_name.removeprefix(settings.tag_prefix)
    action = find_release_action(settings.changelog_dir, version)
    content = read_changelog_section(
        settings.changelog_md.read_text(),
        old_version=action.details.old_version,  # type: ignore
        new_version=action.name,
    )
    output_file = settings.repo_root / f"dist/{tag_name}.changelog.md"
    ensure_parents_write_text(output_file, content)
