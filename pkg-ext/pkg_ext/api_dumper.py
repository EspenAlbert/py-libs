from __future__ import annotations

import inspect
import re
from dataclasses import is_dataclass
from datetime import UTC, datetime
from pydoc import locate
from typing import Any, Callable, get_args, get_origin

from typing_extensions import Annotated
from zero_3rdparty.object_name import as_name

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


def _is_auto_generated_dataclass_doc(cls: type) -> bool:
    """Check if __doc__ is the auto-generated dataclass signature."""
    if not is_dataclass(cls):
        return False
    doc = cls.__doc__
    if not doc:
        return False
    try:
        text_sig = str(inspect.signature(cls)).replace(" -> None", "")
        return doc == cls.__name__ + text_sig
    except (TypeError, ValueError):
        return False


def _get_class_docstring(cls: type) -> str:
    """Get docstring, filtering out auto-generated dataclass signatures."""
    if _is_auto_generated_dataclass_doc(cls):
        return ""
    return cls.__doc__ or ""


def dump_function(symbol: Callable, ref: RefSymbol) -> FunctionDump:
    return FunctionDump(
        name=ref.name,
        module_path=ref.module_path,
        docstring=symbol.__doc__ or "",
        signature=parse_signature(symbol),
        line_number=_get_line_number(symbol),
    )


def dump_class(cls: type, ref: RefSymbol) -> ClassDump:
    fields = parse_class_fields(cls)
    # Skip init_signature when fields present (dataclass/pydantic - init params match fields)
    init_sig = None if fields else parse_signature(cls.__init__)
    return ClassDump(
        name=ref.name,
        module_path=ref.module_path,
        docstring=_get_class_docstring(cls),
        direct_bases=parse_direct_bases(cls),
        init_signature=init_sig,
        fields=fields,
        line_number=_get_line_number(cls),
    )


def dump_exception(cls: type, ref: RefSymbol) -> ExceptionDump:
    return ExceptionDump(
        name=ref.name,
        module_path=ref.module_path,
        docstring=cls.__doc__ or "",
        direct_bases=parse_direct_bases(cls),
        init_signature=parse_signature(cls.__init__),
        line_number=_get_line_number(cls),
    )


_FUNC_REPR_PATTERN = re.compile(r"<function (\w+) at 0x[0-9a-f]+>")

# Generic docstrings from builtin typing constructs that should be filtered out
_GENERIC_DOCSTRING_PREFIXES = (
    "Type variable.",
    "Runtime representation of an annotated type.",
    "Abstract base class for generic types.",
)


def _get_type_alias_docstring(alias: Any) -> str:
    """Get docstring for a type alias, filtering out generic typing docstrings."""
    doc = getattr(alias, "__doc__", "") or ""
    if any(doc.startswith(prefix) for prefix in _GENERIC_DOCSTRING_PREFIXES):
        return ""
    return doc


def _format_value_stable(value: Any) -> str:
    """Format a value with stable output (no memory addresses)."""
    if callable(value) and not isinstance(value, type):
        return as_name(value)
    raw = repr(value)
    return _FUNC_REPR_PATTERN.sub(r"\1", raw)


def _format_type_alias_target(alias: Any) -> str:
    """Format a type alias with stable function references."""
    if alias is None:
        return "unknown"
    if get_origin(alias) is Annotated:
        args = get_args(alias)
        base_type = args[0] if args else alias
        metadata = args[1:] if len(args) > 1 else ()
        base_repr = _format_type_alias_target(base_type)
        meta_reprs = [_format_value_stable(m) for m in metadata]
        return f"typing.Annotated[{base_repr}, {', '.join(meta_reprs)}]"
    raw = str(alias)
    return _FUNC_REPR_PATTERN.sub(r"\1", raw)


def dump_type_alias(alias: Any, ref: RefSymbol) -> TypeAliasDump:
    alias_target = _format_type_alias_target(alias)
    return TypeAliasDump(
        name=ref.name,
        module_path=ref.module_path,
        docstring=_get_type_alias_docstring(alias),
        alias_target=alias_target,
        line_number=_get_line_number(alias),
    )


def dump_global_var(value: Any, ref: RefSymbol) -> GlobalVarDump:
    return GlobalVarDump(
        name=ref.name,
        module_path=ref.module_path,
        docstring="",  # Global vars don't have docstrings
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
