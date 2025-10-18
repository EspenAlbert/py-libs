from __future__ import annotations

import logging
from contextlib import ExitStack
from pathlib import Path
from typing import Self

import typer
from ask_shell._internal.interactive import raise_on_question
from ask_shell._internal.typer_command import configure_logging
from model_lib.model_base import Entity
from pydantic import model_validator
from typer import Typer
from zero_3rdparty.file_utils import iter_paths_and_relative

from pkg_ext.changelog_parser import parse_changelog
from pkg_ext.commit_changelog import add_git_changes
from pkg_ext.errors import NoHumanRequiredError
from pkg_ext.file_parser import parse_code_symbols, parse_symbols
from pkg_ext.gen_changelog_md import write_changelog_md
from pkg_ext.gen_group import write_groups
from pkg_ext.gen_init import write_init
from pkg_ext.gen_pyproject_toml import update_pyproject_toml
from pkg_ext.git_actions import git_commit
from pkg_ext.git_state import GitChangesInput, GitSince, find_git_changes, find_pr_url
from pkg_ext.interactive_choices import on_new_ref
from pkg_ext.models import (
    PkgCodeState,
    pkg_ctx,
)
from pkg_ext.ref_added import (
    handle_added_refs,
)
from pkg_ext.ref_removed import handle_removed_refs
from pkg_ext.settings import PkgSettings, pkg_settings
from pkg_ext.version_bump import bump_or_get_version

app = Typer(name="pkg-ext", help="Generate public API for a package and more!")
logger = logging.getLogger(__name__)


def parse_pkg_code_state(settings: PkgSettings) -> PkgCodeState:
    """PkgDiskState is based only on the current python files in the package"""
    pkg_py_files = list(
        iter_paths_and_relative(settings.pkg_directory, "*.py", only_files=True)
    )
    pkg_import_name = settings.pkg_import_name

    def is_generated(py_text: str) -> bool:
        return py_text.startswith(settings.file_header)

    files = sorted(
        parsed
        for path, rel_path in pkg_py_files
        if (
            parsed := parse_symbols(
                path, rel_path, pkg_import_name, is_generated=is_generated
            )
        )
    )

    import_id_symbols = parse_code_symbols(files, pkg_import_name)
    return PkgCodeState(
        pkg_import_name=pkg_import_name,
        import_id_refs=import_id_symbols,
        files=files,
    )


def create_ctx(
    pkg_path_str: str,
    repo_root: Path,
    skip_open_in_editor: bool,
    dev_mode: bool,
    git_changes_input: GitChangesInput,
) -> pkg_ctx:
    settings = pkg_settings(
        repo_root,
        pkg_path_str,
        skip_open_in_editor=skip_open_in_editor,
        dev_mode=dev_mode,
    )
    code_state = parse_pkg_code_state(settings)
    tool_state, extra_actions = parse_changelog(settings, code_state)
    git_changes = find_git_changes(git_changes_input)
    return pkg_ctx(
        settings=settings,
        tool_state=tool_state,
        code_state=code_state,
        ref_add_callback=[on_new_ref(tool_state.groups)],
        git_changes=git_changes,
        _actions=extra_actions,
    )


argument_pkg_path = typer.Argument(
    ...,
    help="Path to the package directory, expecting pkg_path/__init__.py to exist",
)
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
    GitSince.LAST_GIT_TAG,
    "--git-since",
    help="Will use git log to look for 'fix' commits to include in the changelog",
)
option_bump_version = typer.Option(
    False,
    "--bump",
    help="Use the changelog actions to bump the version",
)
option_no_human = typer.Option(
    False,
    "--no-human",
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

option_push: bool = typer.Option(False, "--push", help="Push commit and tag")


class GenerateApiInput(Entity):
    pkg_path_str: str
    repo_root: Path
    skip_open_in_editor: bool
    dev_mode: bool
    git_changes_since: GitSince
    bump_version: bool
    no_human: bool
    create_tag: bool
    tag_prefix: str
    push: bool

    @model_validator(mode="after")
    def checks(self) -> Self:
        if self.create_tag:
            assert self.bump_version, "cannot tag without bumping version"
        if self.push:
            assert self.create_tag, "cannot push without tagging/committing"
            assert not find_pr_url(self.repo_root), (
                "Never push changes from a branch with an active PR, release jobs only runs from the default branch and wouldn't be triggered leading to tags without releases"
            )
        return self


def _generate_api(api_input: GenerateApiInput) -> None:
    exit_stack = ExitStack()
    if api_input.no_human:
        exit_stack.enter_context(raise_on_question(raise_error=NoHumanRequiredError))
    repo_root = api_input.repo_root
    git_changes_input = GitChangesInput(
        repo_path=repo_root,
        since=api_input.git_changes_since,
    )
    with exit_stack:
        ctx = create_ctx(
            api_input.pkg_path_str,
            repo_root,
            api_input.skip_open_in_editor,
            api_input.dev_mode,
            git_changes_input,
        )
        try:
            with ctx:
                handle_removed_refs(ctx)
                handle_added_refs(ctx)
                add_git_changes(ctx)
                bump_or_get_version(
                    ctx,
                    skip_bump=not api_input.bump_version,
                    add_release_action=api_input.create_tag,
                )
        except KeyboardInterrupt:
            logger.warning(
                f"Interrupted while handling added references, only {ctx.settings.changelog_path} updated"
            )
            return
        write_groups(ctx)
        version = ctx.run_state.current_or_next_version(api_input.bump_version)
        write_init(ctx, version)
        update_pyproject_toml(ctx, version)
        if api_input.create_tag:
            write_changelog_md(ctx, unreleased_version=version)
        else:
            write_changelog_md(ctx)
        if not api_input.create_tag:
            return
        repo_path = ctx.settings.repo_root
        git_tag = f"{api_input.tag_prefix}{version}"
        git_commit(
            repo_path,
            f"chore: pre-release commit for {git_tag}",
            tag=git_tag,
            push=api_input.push,
        )


@app.command()
def pre_push(
    pkg_path_str: str = argument_pkg_path,
    repo_root=option_repo_root,
    git_changes_since: GitSince = option_git_changes_since,
):
    api_input = GenerateApiInput(
        pkg_path_str=pkg_path_str,
        repo_root=repo_root,
        skip_open_in_editor=False,
        dev_mode=True,
        git_changes_since=git_changes_since,
        bump_version=False,
        no_human=False,
        create_tag=False,
        tag_prefix="",
        push=False,
    )
    _generate_api(api_input)


@app.command()
def generate_api(
    pkg_path_str: str = argument_pkg_path,
    repo_root: Path = option_repo_root,
    skip_open_in_editor: bool = option_skip_open_in_editor,
    dev_mode: bool = option_dev_mode,
    git_changes_since: GitSince = option_git_changes_since,
    bump_version: bool = option_bump_version,
    no_human: bool = option_no_human,
    create_tag: bool = option_create_tag,
    tag_prefix: str = option_tag_prefix,
    push: bool = option_push,
):
    api_input = GenerateApiInput(
        pkg_path_str=pkg_path_str,
        repo_root=repo_root,
        skip_open_in_editor=skip_open_in_editor,
        dev_mode=dev_mode,
        git_changes_since=git_changes_since,
        bump_version=bump_version,
        no_human=no_human,
        create_tag=create_tag,
        tag_prefix=tag_prefix,
        push=push,
    )
    _generate_api(api_input)


def main():
    configure_logging(app)
    app()


if __name__ == "__main__":
    main()
