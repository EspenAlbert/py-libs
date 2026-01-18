"""CLI options and arguments for pkg-ext commands."""

from os import getenv

import typer

from pkg_ext.config import load_user_config
from pkg_ext.git_usage import GitSince


def get_default_editor() -> str:
    user_config = load_user_config()
    return user_config.editor or getenv("EDITOR", "code")


option_git_changes_since = typer.Option(
    GitSince.DEFAULT,
    "--git-since",
    help="Will use git log to look for 'fix' commits to include in the changelog",
)

option_bump_version = typer.Option(
    False, "--bump", help="Use the changelog actions to bump the version"
)

option_create_tag = typer.Option(
    False, "--tag", "--commit", help="Add a git commit and tag for the bumped version"
)
option_push = typer.Option(False, "--push", help="Push commit and tag")
option_pr = typer.Option(0, "--pr", help="Use this if the HEAD commit is not a merge")

option_group = typer.Option(
    None, "-g", "--group", help="Generate for specific group only"
)
option_target = typer.Option(
    ..., "--target", "-t", help="Target: group | group.symbol | group.symbol.arg"
)
option_replacement = typer.Option(
    None, "--replacement", "-r", help="Replacement suggestion"
)
option_output_file = typer.Option(None, "-o", "--output", help="Output file path")
option_output_dir = typer.Option(
    None, "-o", "--output-dir", help="Output directory (default: docs/)"
)
option_skip_docs = typer.Option(False, "--skip-docs", help="Skip doc regeneration")
option_skip_clean = typer.Option(
    False, "--skip-clean", help="Skip cleaning old entries"
)
option_skip_dirty_check = typer.Option(
    False, "--skip-dirty-check", help="Skip dirty file check (for tests)"
)
option_dev_mode = typer.Option(
    False, "--dev", help="Write to -dev file (gitignored for local comparison)"
)
option_skip_fix_commits = typer.Option(
    False, "--skip-fix-commits", help="Skip prompts for fix commits in git history"
)
option_full = typer.Option(
    False,
    "--full",
    help="Run pre-commit workflow after pre-change (sync + docs + diff)",
)
