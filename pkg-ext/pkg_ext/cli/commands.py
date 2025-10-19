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
    option_repo_root,
    option_skip_open_in_editor,
    option_tag_prefix,
)
from pkg_ext.cli.workflows import (
    GenerateApiInput,
    generate_api_workflow,
    post_merge_commit_workflow,
)
from pkg_ext.git import GitSince, head_merge_pr

app = Typer(name="pkg-ext", help="Generate public API for a package and more!")


@app.command()
def pre_push(
    pkg_path_str: str = argument_pkg_path,
    repo_root=option_repo_root,
    git_changes_since: GitSince = option_git_changes_since,
):
    """Use this to run before a push. Will ask questions about your changes to ensure the changelog and release can be updated later"""
    api_input = GenerateApiInput(
        pkg_path_str=pkg_path_str,
        repo_root=repo_root,
        skip_open_in_editor=False,
        dev_mode=True,
        git_changes_since=git_changes_since,
        bump_version=False,
        is_bot=False,
        create_tag=False,
        tag_prefix="",
        push=False,
    )
    generate_api_workflow(api_input)


@app.command()
def pre_merge(
    pkg_path_str: str = argument_pkg_path,
    repo_root=option_repo_root,
    git_changes_since: GitSince = option_git_changes_since,
):
    """Use this as a CI check. No merge until this passes. Ensures no manual changes are missing."""
    api_input = GenerateApiInput(
        pkg_path_str=pkg_path_str,
        repo_root=repo_root,
        skip_open_in_editor=True,
        dev_mode=True,
        git_changes_since=git_changes_since,
        bump_version=False,
        is_bot=True,
        create_tag=False,
        tag_prefix="",
        push=False,
    )
    generate_api_workflow(api_input)


@app.command()
def post_merge(
    pkg_path_str: str = argument_pkg_path,
    repo_root=option_repo_root,
    tag_prefix: str = option_tag_prefix,
    explicit_pr: int = typer.Option(
        0, help="Use this if the HEAD commit is not a merge"
    ),
    push: bool = option_push,
):
    """Use this after a merge to bump version, creates the automated release files."""
    from pkg_ext.cli.workflows import create_ctx, sync_files

    pr = explicit_pr or head_merge_pr(Path(repo_root))
    api_input = GenerateApiInput(
        pkg_path_str=pkg_path_str,
        repo_root=repo_root,
        skip_open_in_editor=True,
        dev_mode=False,
        tag_prefix=tag_prefix,
        git_changes_since=GitSince.NO_GIT_CHANGES,  # will not add new entries
        is_bot=True,
        bump_version=True,
        create_tag=True,
        push=push,
    )
    ctx = create_ctx(api_input)
    sync_files(api_input, ctx)
    post_merge_commit_workflow(
        repo_path=repo_root,
        changelog_dir_path=ctx.settings.changelog_path,
        pr_number=pr,
        tag_prefix=tag_prefix,
        new_version=str(ctx.run_state.new_version),
        push=push,
    )


@app.command()
def generate_api(
    pkg_path_str: str = argument_pkg_path,
    repo_root: Path = option_repo_root,
    skip_open_in_editor: bool = option_skip_open_in_editor,
    dev_mode: bool = option_dev_mode,
    git_changes_since: GitSince = option_git_changes_since,
    bump_version: bool = option_bump_version,
    is_bot: bool = option_is_bot,
    create_tag: bool = option_create_tag,
    tag_prefix: str = option_tag_prefix,
    push: bool = option_push,
    explicit_pr: int = typer.Option(
        0, "--pr", help="Use this if the HEAD commit is not a merge"
    ),
):
    api_input = GenerateApiInput(
        pkg_path_str=pkg_path_str,
        repo_root=repo_root,
        skip_open_in_editor=skip_open_in_editor,
        dev_mode=dev_mode,
        git_changes_since=git_changes_since,
        bump_version=bump_version,
        is_bot=is_bot,
        create_tag=create_tag,
        tag_prefix=tag_prefix,
        push=push,
    )
    if ctx := generate_api_workflow(api_input):
        if api_input.create_tag:
            post_merge_commit_workflow(
                repo_path=repo_root,
                changelog_dir_path=ctx.settings.changelog_path,
                pr_number=explicit_pr or ctx.git_changes.current_pr,
                tag_prefix=tag_prefix,
                new_version=str(ctx.run_state.new_version),
                push=push,
            )
