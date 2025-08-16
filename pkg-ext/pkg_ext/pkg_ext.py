from __future__ import annotations

import logging
from pathlib import Path

import typer
from ask_shell._internal._run import run
from ask_shell._internal.interactive import (
    confirm,
)
from ask_shell._internal.typer_command import configure_logging
from model_lib.serialize.parse import parse_model
from typer import Typer
from zero_3rdparty.file_utils import iter_paths_and_relative

from pkg_ext.file_parser import parse_symbols
from pkg_ext.gen_changelog import parse_changelog_actions
from pkg_ext.gen_init import write_init
from pkg_ext.models import (
    PkgCodeState,
    PkgExtState,
    PkgSrcFile,
    PublicGroups,
)
from pkg_ext.ref_added import (
    handle_added_refs,
    parse_code_symbols,
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
    files = sorted(
        parsed
        for path, rel_path in pkg_py_files
        if (parsed := parse_symbols(path, rel_path, pkg_import_name))
    )

    import_id_symbols = parse_code_symbols(files, pkg_import_name)
    return PkgCodeState(import_id_refs=import_id_symbols)


def parse_pkg_ext_state(settings: PkgSettings) -> PkgExtState:
    """The internal state used by pkg-ext to generate files"""
    state_dir = settings.state_dir
    public_groups_path = state_dir / PublicGroups.STORAGE_FILENAME
    if public_groups_path.exists():
        public_groups = parse_model(public_groups_path, t=PublicGroups)
        public_groups.storage_path = public_groups_path
    else:
        public_groups = PublicGroups(storage_path=public_groups_path)
    changelog_path = settings.changelog_path
    changelog_path.mkdir(parents=True, exist_ok=True)
    actions = parse_changelog_actions(changelog_path)
    ref_state = PkgExtState(
        changelog_dir=changelog_path,
        pkg_path=settings.pkg_directory,
        groups=public_groups,
    )
    for action in actions:
        ref_state.update_state(action)
    return ref_state


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
):
    settings = pkg_settings(repo_root, pkg_path_str)
    repo_dir = settings.repo_root
    pre_push = run("just pre-push", cwd=repo_dir)
    cov_full = run("just cov-full xml", cwd=repo_dir)
    assert pre_push or cov_full, "todo: use results instead"
    code_state = parse_pkg_code_state(settings)
    tool_state = parse_pkg_ext_state(settings)
    try:
        with tool_state.changelog_updater() as add_changelog_action:
            handle_removed_refs(
                tool_state, code_state, add_changelog_action
            )  # updates the changelog state
            handle_added_refs(
                tool_state, code_state, add_changelog_action
            )  # updates the changelog and group state
    except KeyboardInterrupt:
        logger.warning("Interrupted while handling added references")
    # todo: Change me to be grouped instead!
    if exposed_refs := tool_state.exposed_refs(code_state.named_refs):
        if confirm(
            "Do you want to write __init__.py with exposed references?", default=True
        ):
            write_init(
                settings.init_path,
                exposed_refs,
                [
                    src_file
                    for src_file in code_state
                    if isinstance(src_file, PkgSrcFile)
                ],
            )


def main():
    configure_logging(app)
    app()


if __name__ == "__main__":
    main()
