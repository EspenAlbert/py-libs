from pathlib import Path

from pkg_ext.models import (
    PkgCodeState,
    PublicGroup,
    SymbolRefId,
    pkg_ctx,
    ref_id_module,
    ref_id_name,
)
from pkg_ext.settings import PkgSettings


def as_import_line(
    pkg_name: str, ref: SymbolRefId, *, skip_as_alias_underscore: bool = False
) -> str:
    if skip_as_alias_underscore:
        return f"from {pkg_name}.{ref_id_module(ref)} import {ref_id_name(ref)}"

    return f"from {pkg_name}.{ref_id_module(ref)} import {ref_id_name(ref)} as _{ref_id_name(ref)}"


def write_imports(code: PkgCodeState, refs: list[SymbolRefId]) -> list[str]:
    return [as_import_line(code.pkg_import_name, ref) for ref in code.sort_refs(refs)]


def write_group(group: PublicGroup, settings: PkgSettings, code: PkgCodeState) -> Path:
    path = settings.pkg_directory / f"{group.name}.py"
    pkg_name = code.pkg_import_name
    imports = [as_import_line(pkg_name, ref) for ref in group.sorted_refs]
    exposed_vars = [
        f"{ref_id_name(ref)} = _{ref_id_name(ref)}" for ref in group.sorted_refs
    ]
    file_content = "\n".join(
        [
            settings.file_header,
            *imports,
            "",
            *exposed_vars,
            "",
        ]
    )
    path.write_text(file_content)
    return path


def write_groups(ctx: pkg_ctx) -> list[Path]:
    return [
        write_group(group, ctx.settings, ctx.code_state)
        for group in ctx.tool_state.groups.groups_no_root
    ]
