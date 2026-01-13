from zero_3rdparty.iter_utils import flat_map

from pkg_ext.context import pkg_ctx
from pkg_ext.generation.groups import as_import_line
from pkg_ext.models import PublicGroup, SymbolRefId
from pkg_ext.warnings_gen import get_warning_class_names


def write_init(ctx: pkg_ctx, version: str):
    settings = ctx.settings
    code = ctx.code_state
    tool_state = ctx.tool_state
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

    warning_imports: list[str] = []
    warning_classes: list[str] = []
    if settings.warnings_file_path.exists():
        warning_classes = get_warning_class_names(pkg_name)
        warning_imports = [
            f"from {pkg_name}._warnings import {', '.join(warning_classes)}"
        ]

    init_lines = [
        settings.file_header,
        "# flake8: noqa",
        *import_lines,
        *warning_imports,
        "",
        f'VERSION = "{version}"',
        "__all__ = [",
        *[f'    "{name}",' for name in all_symbols],
        *[f'    "{name}",' for name in warning_classes],
        "]",
    ]
    settings.init_path.write_text("\n".join(init_lines) + "\n")
