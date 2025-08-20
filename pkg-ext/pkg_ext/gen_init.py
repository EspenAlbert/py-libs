import logging

from zero_3rdparty.iter_utils import flat_map

from pkg_ext.gen_group import as_import_line
from pkg_ext.models import (
    PkgCodeState,
    PkgExtState,
    PublicGroup,
    SymbolRefId,
)
from pkg_ext.settings import PkgSettings

logger = logging.getLogger(__name__)


def write_init(tool_state: PkgExtState, code: PkgCodeState, settings: PkgSettings):
    pkg_name = code.pkg_import_name
    sorted_symbols = code.sort_refs(
        flat_map(group.owned_refs for group in tool_state.groups.groups)
    )
    symbol_groups: dict[SymbolRefId, PublicGroup] = {}
    for group in tool_state.groups.groups:
        for ref in group.owned_refs:
            symbol_groups[ref] = group

    import_lines: list[str] = []
    groups_imported: set[str] = set()
    for symbol in sorted_symbols:
        group = symbol_groups[symbol]
        if group.is_root:
            import_lines.append(
                as_import_line(pkg_name, symbol, skip_as_alias_underscore=True)
            )
            continue
        group_name = group.name
        if group_name in groups_imported:
            continue
        import_lines.append(f"from {pkg_name} import {group_name}")
        groups_imported.add(group_name)
    all_symbols = [line.split(" ")[-1] for line in import_lines]
    init_lines = [
        settings.file_header,
        "# flake8: noqa",
        *import_lines,
        "",
        "__all__ = [",
        *[f'    "{name}",' for name in all_symbols],
        "]",
    ]
    settings.init_path.write_text("\n".join(init_lines) + "\n")
