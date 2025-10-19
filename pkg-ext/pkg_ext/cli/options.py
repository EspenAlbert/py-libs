"""CLI options and arguments for pkg-ext commands."""

from os import getenv

import typer

from pkg_ext.config import load_user_config
from pkg_ext.git_usage import GitSince


def get_default_editor() -> str:
    """Get default editor from user config with fallback to EDITOR env var."""
    user_config = load_user_config()
    return user_config.editor or getenv("EDITOR", "code")


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

option_create_tag = typer.Option(
    False,
    "--tag",
    "--commit",
    help="Add a git commit and tag for the bumped version",
)
option_push = typer.Option(False, "--push", help="Push commit and tag")
option_pr = typer.Option(0, "--pr", help="Use this if the HEAD commit is not a merge")
