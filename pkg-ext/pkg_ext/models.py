from __future__ import annotations

from contextlib import suppress
from functools import total_ordering
from pathlib import Path
from pydoc import locate
from typing import Iterable

from ask_shell._internal.interactive import ChoiceTyped
from model_lib.model_base import Entity
from pydantic import Field, ValidationError, model_validator
from zero_3rdparty.enum_utils import StrEnum


def ref_id(rel_path: str, symbol_name: str) -> str:
    """Generate a unique reference ID based on the relative path and symbol name."""
    return f"{rel_path.removesuffix('.py')}:{symbol_name}"


def is_test_file(path: Path) -> bool:
    return (
        path.name.startswith("test_")
        or path.name.endswith("_test.py")
        or path.name == "conftest.py"
    )


class SymbolType(StrEnum):
    TYPE_ALIAS = "type_alias"
    GLOBAL_VAR = "global_var"
    FUNCTION = "function"
    CLASS = "class"
    EXCEPTION = "exception"


@total_ordering
class RefSymbol(Entity):
    name: str = Field(description="Symbol name")
    type: SymbolType = Field(
        description=f"Type of the symbol, one of SymbolType: {list(SymbolType)}"
    )
    rel_path: str = Field(
        description="Relative path to the file where the symbol is defined"
    )
    docstring: str = Field(
        default="", description="Docstring of the symbol, if available", init=False
    )
    src_usages: list[str] = Field(
        default_factory=list,
        description="List of source file relative paths where the symbol is used",
        init=False,
    )
    test_usages: list[str] = Field(
        default_factory=list,
        description="List of test file relative paths where the symbol is used",
        init=False,
    )

    def __str__(self) -> str:
        return f"{self.name} ({self.type}) in {self.rel_path}"

    def __lt__(self, other) -> bool:
        if not isinstance(other, RefSymbol):
            raise TypeError
        return self.local_id < other.local_id

    @model_validator(mode="after")
    def ensure_valid_name(self):
        assert self.name, "Symbol name cannot be empty"
        if self.name[0] == "_":
            raise ValueError(
                f"Symbol name {self.name} cannot start with '_', '_' is reserved for private symbols"
            )
        match self.type:
            case SymbolType.TYPE_ALIAS if not self.name.endswith("T"):
                raise ValueError(f"Type alias {self.name} should end with 'T'")
            case SymbolType.GLOBAL_VAR if not self.name.isupper() or len(self.name) < 2:
                raise ValueError(
                    f"Global variable {self.name} should be in uppercase and longer than 1 character"
                )
            case SymbolType.EXCEPTION if not self.name.endswith("Error"):
                raise ValueError(f"Exception {self.name} should end with 'Error'")
        self.docstring = locate(self.local_id).__doc__ or ""
        return self

    @property
    def local_id(self) -> str:
        """Without the top level package name."""
        return ref_id(self.rel_path, self.name)

    def full_id(self, pkg_import_name: str) -> str:
        """Full ID including the package name."""
        return f"{pkg_import_name}.{self.local_id}"

    def as_choice(self, checked: bool) -> ChoiceTyped:
        test_usages_str = (
            ", ".join(self.test_usages) if self.test_usages else "No test usages"
        )
        src_usages_str = (
            ", ".join(self.src_usages) if self.src_usages else "No source usages"
        )
        return ChoiceTyped(
            name=f"{self.name} {self.type} {len(self.src_usages)} src usages {len(self.test_usages)} test usages",
            value=self.name,
            description=f"{self.docstring}\nSource usages: {src_usages_str}\nTest usages: {test_usages_str}",
            checked=checked,
        )


@total_ordering
class PkgFileBase(Entity):
    path: Path
    relative_path: str
    pkg_import_name: str = Field(description="Name of the package")
    local_imports: set[str] = Field(
        default_factory=set
    )  # should be in the format of ref_id (see `ref_id` function)

    @property
    def module_full_name(self) -> str:
        """Get the module name based on the package import name and relative path."""
        return f"{self.pkg_import_name}.{self.relative_path.removesuffix('.py').replace('/', '.')}"

    def depends_on(self, other: PkgFileBase) -> bool:
        """Check if this package file depends on another package file."""
        if not isinstance(other, PkgFileBase):
            raise TypeError(f"Expected PkgFileBase, got {type(other)}")
        other_import_name = other.module_full_name
        other_import_ref = f"{other_import_name}:"
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


def is_dunder_file(path: Path) -> bool:
    return path.stem.startswith("__") and path.stem.endswith("__")


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


class RefStateType(StrEnum):
    UNSET = "unset"
    EXPOSED = "exposed"
    HIDDEN = "hidden"
    DEPRECATED = "deprecated"
    DELETED = "deleted"


class RefState(Entity):
    name: str
    type: RefStateType = RefStateType.UNSET

    def as_choice(self) -> ChoiceTyped:
        return ChoiceTyped(
            name=self.name, value=self.name, description=f"State: {self.type.value}"
        )


class RefStateWithSymbol(RefState):
    symbol: RefSymbol = Field(
        description="Reference symbol, should be set for this state"
    )

    def as_choice(self) -> ChoiceTyped:
        return ChoiceTyped(
            name=self.symbol.local_id,
            value=self.name,
            description=self.symbol.docstring,
        )
