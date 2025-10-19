"""CLI options and arguments for pkg-ext commands."""

from pathlib import Path

import typer

from pkg_ext.git import GitSince

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
    False,
    "--skip-open",
    help="By default files are opened in $EDITOR when asked to expose/hide",
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
    "",
    "--tag-prefix",
    help="{tag_prefix}{version} used in the git tag not in the version",
)

option_push = typer.Option(False, "--push", help="Push commit and tag")
