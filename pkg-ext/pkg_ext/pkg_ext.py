from __future__ import annotations

import logging
from pathlib import Path

import typer
from ask_shell._internal.interactive import (
    confirm,
)
from ask_shell._internal.typer_command import configure_logging
from model_lib.serialize.parse import parse_model
from typer import Typer
from zero_3rdparty.file_utils import iter_paths_and_relative

from pkg_ext.file_parser import parse_symbols
from pkg_ext.gen_init import write_init
from pkg_ext.models import (
    PkgSrcFile,
    PublicGroups,
)
from pkg_ext.ref_processor import (
    create_ref_state,
    create_refs,
    handle_added_refs,
    handle_removed_refs,
    named_refs,
)
from pkg_ext.settings import pkg_settings

app = Typer(name="pkg-ext", help="Generate public API for a package and more!")
logger = logging.getLogger(__name__)


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
    # repo_dir = settings.repo_root
    # pre_push = run("just pre-push", cwd=repo_dir)
    # cov_full = run("just cov-full xml", cwd=repo_dir)
    # # TODO: support checking these results
    pkg_path = settings.pkg_directory
    state_dir = settings.state_dir
    public_groups_path = state_dir / PublicGroups.STORAGE_FILENAME
    if public_groups_path.exists():
        public_groups = parse_model(public_groups_path, t=PublicGroups)
        public_groups.storage_path = public_groups_path
    else:
        public_groups = PublicGroups(storage_path=public_groups_path)
    pkg_py_files = list(iter_paths_and_relative(pkg_path, "*.py", only_files=True))
    pkg_import_name = settings.pkg_import_name
    parsed_files = sorted(
        parsed
        for path, rel_path in pkg_py_files
        if (parsed := parse_symbols(path, rel_path, pkg_import_name))
    )
    import_id_symbols = create_refs(parsed_files, pkg_import_name)
    active_states = named_refs(import_id_symbols)
    changelog_dir_path = settings.changelog_path
    changelog_dir_path.mkdir(parents=True, exist_ok=True)
    state = create_ref_state(pkg_path, changelog_dir_path)
    handle_removed_refs(state, active_states)

    # Todo: Handle changed refs by inspecting signatures
    try:
        # TODO: Support also grouping the references
        handle_added_refs(state, active_states, public_groups)
    except KeyboardInterrupt:
        logger.warning("Interrupted while handling added references")
    if exposed_refs := state.exposed_refs(active_states):
        if confirm(
            "Do you want to write __init__.py with exposed references?", default=True
        ):
            write_init(
                settings.init_path,
                exposed_refs,
                [
                    src_file
                    for src_file in parsed_files
                    if isinstance(src_file, PkgSrcFile)
                ],
            )


def main():
    configure_logging(app)
    app()


if __name__ == "__main__":
    main()
