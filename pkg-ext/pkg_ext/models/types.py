from __future__ import annotations

from pathlib import Path
from typing import Annotated, TypeAlias

from pydantic import AfterValidator


def ref_id_format(original: str):
    if "." not in original:
        raise ValueError(
            f"A ref_id must use the form parent.child:function module format, got: {original}"
        )
    return original


def as_module_path(rel_path: str) -> str:
    return rel_path.removesuffix(".py").replace("/", ".")


def is_root_identifier(value: str):
    if value.isidentifier():
        return value
    raise ValueError(
        f"invalid python identifier: {value}, must not use . and be valid module name"
    )


def is_test_file(path: Path) -> bool:
    return (
        path.name.startswith("test_")
        or path.name.endswith("_test.py")
        or path.name == "conftest.py"
    )


def is_dunder_file(path: Path) -> bool:
    return path.stem.startswith("__") and path.stem.endswith("__")


SymbolRefId: TypeAlias = Annotated[str, AfterValidator(ref_id_format)]
PyIdentifier: TypeAlias = Annotated[str, AfterValidator(is_root_identifier)]


def ref_id_module(ref_id: SymbolRefId) -> str:
    return ref_id.rsplit(".", maxsplit=1)[0]


def ref_id_name(ref_id: SymbolRefId) -> str:
    return ref_id.rsplit(".", maxsplit=1)[-1]


def ref_id(rel_path: str, symbol_name: str) -> SymbolRefId:
    """Generate a pydoc.locate(ref_id) compatible id."""
    return f"{as_module_path(rel_path)}.{symbol_name}"
