from __future__ import annotations

from contextlib import suppress
from functools import total_ordering
from pathlib import Path
from typing import Iterable

from model_lib.model_base import Entity
from pydantic import Field, ValidationError, model_validator

from .py_symbols import RefSymbol, SymbolType
from .types import as_module_path, is_dunder_file, is_test_file


@total_ordering
class PkgFileBase(Entity):
    path: Path
    relative_path: str
    pkg_import_name: str = Field(description="Name of the package")
    local_imports: set[str] = Field(
        default_factory=set
    )  # should be in the format of ref_id (see `ref_id` function)
    dependencies: set[PkgFileBase] = Field(
        default_factory=set, description="Added by the PkgCodeState"
    )

    @property
    def module_local_path(self) -> str:
        return as_module_path(self.relative_path)

    @property
    def module_full_name(self) -> str:
        """Get the module name based on the package import name and relative path."""
        return f"{self.pkg_import_name}.{self.module_local_path}"

    def depends_on(self, other: PkgFileBase) -> bool:
        """Check if this package file depends on another package file."""
        if not isinstance(other, PkgFileBase):
            raise TypeError(f"Expected PkgFileBase, got {type(other)}")
        return other in self.dependencies

    def _depend_from_import(self, other: PkgFileBase) -> bool:
        other_import_name = other.module_full_name
        other_import_ref = f"{other_import_name}."
        return any(
            ref.startswith(other_import_ref) or ref == other_import_name
            for ref in self.local_imports
        )

    def iterate_ref_symbols(self) -> Iterable[RefSymbol]:
        yield from []

    def iterate_usage_ids(self) -> Iterable[str]:
        yield from self.local_imports

    def __lt__(self, other) -> bool:
        if not isinstance(other, PkgFileBase):
            raise TypeError
        if self.depends_on(other):
            return False
        if other.depends_on(self):
            return True
        return self.relative_path < other.relative_path

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, PkgFileBase):
            raise TypeError
        return self.path == value.path

    def __hash__(self) -> int:
        return hash(self.path)


class PkgSrcFile(PkgFileBase):
    type_aliases: list[str] = Field(default_factory=list)
    global_vars: list[str] = Field(default_factory=list)
    functions: list[str] = Field(default_factory=list)
    classes: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_not_a_test(self):
        if is_test_file(self.path):
            raise ValueError(f"File {self.path} is a test file, not a src file.")
        if is_dunder_file(self.path):
            raise ValueError(f"File {self.path} is a dunder file, not a src file.")
        return self

    def iterate_ref_symbols(self) -> Iterable[RefSymbol]:
        def yield_safely(symbol_name: str, symbol_type: SymbolType):
            with suppress(ValidationError):
                yield RefSymbol(
                    name=symbol_name,
                    type=symbol_type,
                    rel_path=self.relative_path,
                )

        for symbol_name in self.type_aliases:
            yield from yield_safely(symbol_name, SymbolType.TYPE_ALIAS)
        for symbol_name in self.global_vars:
            yield from yield_safely(symbol_name, SymbolType.GLOBAL_VAR)
        for symbol_name in self.functions:
            yield from yield_safely(symbol_name, SymbolType.FUNCTION)
        for symbol_name in self.classes:
            yield from yield_safely(symbol_name, SymbolType.CLASS)
        for symbol_name in self.exceptions:
            yield from yield_safely(symbol_name, SymbolType.EXCEPTION)


class PkgTestFile(PkgFileBase):
    @model_validator(mode="after")
    def ensure_is_a_test(self):
        if not is_test_file(self.path):
            raise ValueError(f"File {self.path} is not a test file.")
        return self
