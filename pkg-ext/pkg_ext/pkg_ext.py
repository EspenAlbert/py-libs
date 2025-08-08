from __future__ import annotations

import logging
from pathlib import Path

import typer
from ask_shell._internal.interactive import (
    confirm,
)
from ask_shell._internal.typer_command import configure_logging
from typer import Typer
from zero_3rdparty.file_utils import iter_paths_and_relative

from pkg_ext.file_parser import parse_symbols
from pkg_ext.gen_init import write_init
from pkg_ext.models import (
    PkgSrcFile,
)
from pkg_ext.ref_processor import (
    create_ref_state,
    create_refs,
    handle_added_refs,
    handle_removed_refs,
    named_refs,
)

app = Typer(name="pkg-ext", help="Generate public API for a package and more!")
logger = logging.getLogger(__name__)


@app.command()
def generate_api(
    pkg_path_str: str = typer.Argument(
        ...,
        help="Path to the package directory, expecting pkg_path/__init__.py to exist",
    ),
):
    pkg_path = Path(pkg_path_str).resolve()
    assert pkg_path.is_dir(), f"Expected a directory, got {pkg_path}"
    init_file = pkg_path / "__init__.py"
    assert init_file.is_file(), f"Expected {init_file} to exist"
    pkg_py_files = list(iter_paths_and_relative(pkg_path, "*.py", only_files=True))
    pkg_import_name = pkg_path.name
    parsed_files = sorted(
        parsed
        for path, rel_path in pkg_py_files
        if (parsed := parse_symbols(path, rel_path, pkg_import_name))
    )
    import_id_symbols = create_refs(parsed_files, pkg_import_name)
    active_states = named_refs(import_id_symbols)
    changelog_dir_path = init_file.parent.parent / ".changelog"
    changelog_dir_path.mkdir(parents=True, exist_ok=True)
    state = create_ref_state(pkg_path, changelog_dir_path)
    handle_removed_refs(state, active_states)
    # Todo: Handle changed refs by inspecting signatures
    try:
        handle_added_refs(state, active_states)
    except KeyboardInterrupt:
        logger.warning("Interrupted while handling added references")
    if exposed_refs := state.exposed_refs(active_states):
        if confirm(
            "Do you want to write __init__.py with exposed references?", default=True
        ):
            write_init(
                init_file,
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
