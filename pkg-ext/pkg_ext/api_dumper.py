from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pydoc import locate
from typing import Any, Callable

from pkg_ext.models.api_dump import (
    ClassDump,
    ExceptionDump,
    FunctionDump,
    GlobalVarDump,
    GroupDump,
    PublicApiDump,
    SymbolDump,
    TypeAliasDump,
)
from pkg_ext.models.groups import PublicGroup, PublicGroups
from pkg_ext.models.py_symbols import RefSymbol, SymbolType
from pkg_ext.pkg_state import PkgExtState
from pkg_ext.signature_parser import (
    parse_class_fields,
    parse_direct_bases,
    parse_signature,
)


def _resolve_symbol(ref: RefSymbol, pkg_import_name: str) -> Any:
    full_path = ref.full_id(pkg_import_name)
    return locate(full_path)


def _get_line_number(obj: Any) -> int | None:
    try:
        _, line = inspect.getsourcelines(obj)
        return line
    except (OSError, TypeError):
        return None


def dump_function(symbol: Callable, ref: RefSymbol) -> FunctionDump:
    return FunctionDump(
        name=ref.name,
        module_path=ref.module_path,
        docstring=ref.docstring,
        signature=parse_signature(symbol),
        line_number=_get_line_number(symbol),
    )


def dump_class(cls: type, ref: RefSymbol) -> ClassDump:
    return ClassDump(
        name=ref.name,
        module_path=ref.module_path,
        docstring=ref.docstring,
        direct_bases=parse_direct_bases(cls),
        init_signature=parse_signature(cls.__init__),
        fields=parse_class_fields(cls),
        line_number=_get_line_number(cls),
    )


def dump_exception(cls: type, ref: RefSymbol) -> ExceptionDump:
    return ExceptionDump(
        name=ref.name,
        module_path=ref.module_path,
        docstring=ref.docstring,
        direct_bases=parse_direct_bases(cls),
        init_signature=parse_signature(cls.__init__),
        line_number=_get_line_number(cls),
    )


def dump_type_alias(alias: Any, ref: RefSymbol) -> TypeAliasDump:
    alias_target = str(alias) if alias else "unknown"
    return TypeAliasDump(
        name=ref.name,
        module_path=ref.module_path,
        docstring=ref.docstring,
        alias_target=alias_target,
        line_number=_get_line_number(alias),
    )


def dump_global_var(value: Any, ref: RefSymbol) -> GlobalVarDump:
    return GlobalVarDump(
        name=ref.name,
        module_path=ref.module_path,
        docstring=ref.docstring,
        value_repr=repr(value) if value is not None else None,
    )


def dump_symbol(ref: RefSymbol, pkg_import_name: str) -> SymbolDump | None:
    symbol = _resolve_symbol(ref, pkg_import_name)
    if symbol is None:
        return None
    match ref.type:
        case SymbolType.FUNCTION:
            return dump_function(symbol, ref)
        case SymbolType.CLASS:
            return dump_class(symbol, ref)
        case SymbolType.EXCEPTION:
            return dump_exception(symbol, ref)
        case SymbolType.TYPE_ALIAS:
            return dump_type_alias(symbol, ref)
        case SymbolType.GLOBAL_VAR:
            return dump_global_var(symbol, ref)
    return None


def dump_group(
    group: PublicGroup,
    refs: dict[str, RefSymbol],
    pkg_import_name: str,
) -> GroupDump:
    symbols: list[SymbolDump] = []
    for ref_id in sorted(group.owned_refs):
        ref = refs.get(ref_id)
        if ref is None:
            continue
        if symbol_dump := dump_symbol(ref, pkg_import_name):
            symbols.append(symbol_dump)
    return GroupDump(name=group.name, symbols=symbols)


def dump_public_api(
    state: PkgExtState,
    groups: PublicGroups,
    refs: dict[str, RefSymbol],
    pkg_import_name: str,
    version: str,
) -> PublicApiDump:
    group_dumps = [
        dump_group(group, refs, pkg_import_name)
        for group in groups.groups
        if not group.is_root
    ]
    root_group = groups.root_group
    if root_group.owned_refs:
        group_dumps.insert(0, dump_group(root_group, refs, pkg_import_name))
    return PublicApiDump(
        pkg_import_name=pkg_import_name,
        version=version,
        groups=group_dumps,
        dumped_at=datetime.now(UTC),
    )
