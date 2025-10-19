"""CLI options and arguments for pkg-ext commands."""

from os import getenv
from pathlib import Path

import typer

from pkg_ext.config import load_user_config
from pkg_ext.git import GitSince


def get_default_editor() -> str:
    """Get default editor from user config with fallback to EDITOR env var."""
    user_config = load_user_config()
    return user_config.editor or getenv("EDITOR", "code")


# Argument definitions
argument_pkg_path = typer.Argument(
    ...,
    help="Path to the package directory, expecting pkg_path/__init__.py to exist",
)

# Option definitions
option_repo_root = typer.Option(
    ...,
    "-r",
    "--repo-root",
    default_factory=Path.cwd,
)

option_skip_open_in_editor = typer.Option(
    None,
    "--skip-open",
    envvar="PKG_EXT_SKIP_OPEN_IN_EDITOR",
    help="Skip opening files in editor. Uses user config or env var if not set explicitly.",
)

option_dev_mode = typer.Option(
    False,
    "--dev",
    help="Adds a '-dev' suffix to files to avoid any merge conflicts",
)

option_git_changes_since = typer.Option(
    GitSince.DEFAULT,
    "--git-since",
    help="Will use git log to look for 'fix' commits to include in the changelog",
)

option_bump_version = typer.Option(
    False,
    "--bump",
    help="Use the changelog actions to bump the version",
)

option_is_bot = typer.Option(
    False,
    "--is-bot",
    help="For CI to avoid any prompt hanging or accidental defaults made",
)

option_create_tag = typer.Option(
    False,
    "--tag",
    "--commit",
    help="Add a git commit and tag for the bumped version",
)

option_tag_prefix = typer.Option(
    None,
    "--tag-prefix",
    envvar="PKG_EXT_TAG_PREFIX",
    help="{tag_prefix}{version} used in the git tag. Uses project config or env var if not set.",
)

option_push = typer.Option(False, "--push", help="Push commit and tag")
