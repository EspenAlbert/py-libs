from __future__ import annotations

import logging
from contextlib import ExitStack
from pathlib import Path

import typer
from ask_shell._internal.interactive import raise_on_question
from ask_shell._internal.typer_command import configure_logging
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
from pkg_ext.git_state import GitChangesInput, GitSince, find_git_changes
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
    git_changes_since: GitSince,
) -> pkg_ctx:
    settings = pkg_settings(
        repo_root,
        pkg_path_str,
        skip_open_in_editor=skip_open_in_editor,
        dev_mode=dev_mode,
    )
    code_state = parse_pkg_code_state(settings)
    tool_state, extra_actions = parse_changelog(settings, code_state)
    git_changes = find_git_changes(
        GitChangesInput(repo_path=settings.repo_root, since=git_changes_since)
    )
    return pkg_ctx(
        settings=settings,
        tool_state=tool_state,
        code_state=code_state,
        ref_add_callback=[on_new_ref(tool_state.groups)],
        git_changes=git_changes,
        _actions=extra_actions,
    )


@app.command()
def generate_api(
    pkg_path_str: str = typer.Argument(
        ...,
        help="Path to the package directory, expecting pkg_path/__init__.py to exist",
    ),
    repo_root: Path = typer.Option(
        ...,
        "-r",
        "--repo-root",
        default_factory=Path.cwd,
    ),
    skip_open_in_editor: bool = typer.Option(
        False,
        "--skip-open",
        help="By default files are opened in $EDITOR when asked to expose/hide",
    ),
    dev_mode: bool = typer.Option(
        False,
        "--dev",
        help="Adds a '-dev' suffix to files to avoid any merge conflicts",
    ),
    git_changes_since: GitSince = typer.Option(
        GitSince.LAST_GIT_TAG,
        "--git-since",
        help="Will use git log to look for 'fix' commits to include in the changelog",
    ),
    bump_version: bool = typer.Option(
        False,
        "--bump",
        help="Use the changelog actions to bump the version",
    ),
    no_human: bool = typer.Option(
        False,
        "--no-human",
        help="For CI to avoid any prompt hanging or accidental defaults made",
    ),
    create_tag: bool = typer.Option(
        False,
        "--tag",
        "--commit",
        help="Add a git commit and tag for the bumped version",
    ),
    tag_prefix: str = typer.Option(
        "",
        "--tag-prefix",
        help="{tag_prefix}{version} used in the git tag not in the version",
    ),
    push: bool = typer.Option(False, "--push", help="Push commit and tag"),
):
    if create_tag:
        assert bump_version, "cannot tag without bumping version"
    if push:
        assert create_tag, "cannot push without tagging/committing"
    exit_stack = ExitStack()
    if no_human:
        exit_stack.enter_context(raise_on_question(raise_error=NoHumanRequiredError))
    with exit_stack:
        ctx = create_ctx(
            pkg_path_str, repo_root, skip_open_in_editor, dev_mode, git_changes_since
        )
        try:
            with ctx:
                handle_removed_refs(ctx)
                handle_added_refs(ctx)
                add_git_changes(ctx)
                bump_or_get_version(
                    ctx,
                    skip_bump=not bump_version,
                    add_release_action=create_tag,
                )
        except KeyboardInterrupt:
            logger.warning(
                f"Interrupted while handling added references, only {ctx.settings.changelog_path} updated"
            )
            return
        write_groups(ctx)
        version = ctx.run_state.current_or_next_version(bump_version)
        write_init(ctx, version)
        update_pyproject_toml(ctx, version)
        write_changelog_md(ctx)
        if not create_tag:
            return
        repo_path = ctx.settings.repo_root
        git_tag = f"{tag_prefix}{version}"
        git_commit(
            repo_path,
            f"chore: pre-release commit for {git_tag}",
            tag=git_tag,
            push=push,
        )


def main():
    configure_logging(app)
    app()


if __name__ == "__main__":
    main()
