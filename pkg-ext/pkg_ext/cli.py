from __future__ import annotations

import logging
from pathlib import Path

import typer
from ask_shell._internal.typer_command import configure_logging
from typer import Typer
from zero_3rdparty.file_utils import iter_paths_and_relative

from pkg_ext.commit_changelog import add_git_changes
from pkg_ext.errors import NoPublicGroupMatch
from pkg_ext.file_parser import parse_code_symbols, parse_symbols
from pkg_ext.gen_changelog import ChangelogAction, ChangelogActionType, GroupModulePath
from pkg_ext.gen_group import write_groups
from pkg_ext.gen_init import write_init
from pkg_ext.git_state import GitChangesInput, GitSince, find_git_changes
from pkg_ext.interactive_choices import select_group
from pkg_ext.models import (
    PkgCodeState,
    PkgExtState,
    PublicGroups,
    RefAddCallback,
    RefSymbol,
    pkg_ctx,
)
from pkg_ext.ref_added import (
    handle_added_refs,
)
from pkg_ext.ref_removed import handle_removed_refs
from pkg_ext.settings import PkgSettings, pkg_settings

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


def on_new_ref(groups: PublicGroups) -> RefAddCallback:
    def on_ref(ref: RefSymbol) -> ChangelogAction | None:
        try:
            found_group = groups.matching_group(ref)
            groups.add_ref(ref, found_group.name)
        except NoPublicGroupMatch:
            new_group = select_group(groups, ref)
            return ChangelogAction(
                name=new_group.name,
                action=ChangelogActionType.GROUP_MODULE,
                details=GroupModulePath(module_path=ref.module_path),
            )

    return on_ref


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
        help="will use git log to look for 'fix' commits to include in the changelog",
    ),
):
    settings = pkg_settings(
        repo_root,
        pkg_path_str,
        skip_open_in_editor=skip_open_in_editor,
        dev_mode=dev_mode,
    )
    code_state = parse_pkg_code_state(settings)
    tool_state = PkgExtState.parse(settings)
    git_changes = (
        None
        if git_changes_since == GitSince.NO_GIT_CHANGES
        else find_git_changes(
            GitChangesInput(repo_path=settings.repo_root, since=git_changes_since)
        )
    )
    ctx = pkg_ctx(
        settings=settings,
        tool_state=tool_state,
        code_state=code_state,
        ref_add_callback=[on_new_ref(tool_state.groups)],
        git_changes=git_changes,
    )
    try:
        with ctx:
            add_git_changes(ctx)
            handle_removed_refs(
                tool_state, code_state, ctx
            )  # updates the changelog state
            handle_added_refs(
                tool_state, code_state, ctx, settings
            )  # updates the changelog and group state
    except KeyboardInterrupt:
        logger.warning("Interrupted while handling added references")
    write_groups(tool_state, code_state, settings)
    write_init(tool_state, code_state, settings)


def main():
    configure_logging(app)
    app()


if __name__ == "__main__":
    main()
