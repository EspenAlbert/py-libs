from __future__ import annotations

from functools import total_ordering
from pydoc import locate

from model_lib.model_base import Entity
from pydantic import Field, model_validator
from zero_3rdparty.enum_utils import StrEnum

from .types import SymbolRefId, as_module_path, ref_id


class SymbolType(StrEnum):
    TYPE_ALIAS = "type_alias"
    GLOBAL_VAR = "global_var"
    FUNCTION = "function"
    CLASS = "class"
    EXCEPTION = "exception"
    UNKNOWN = "unknown"


@total_ordering
class RefSymbol(Entity):
    name: str = Field(description="Symbol name")
    type: SymbolType = Field(
        description=f"Type of the symbol, one of SymbolType: {list(SymbolType)}"
    )
    rel_path: str = Field(
        description="Relative path to the file where the symbol is defined without"
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
    def local_id(self) -> SymbolRefId:
        """Without the top level package name."""
        return ref_id(self.rel_path, self.name)

    @property
    def module_path(self) -> str:
        return as_module_path(self.rel_path)

    def full_id(self, pkg_import_name: str) -> str:
        """Full ID including the package name."""
        return f"{pkg_import_name}.{self.local_id}"

    @property
    def is_type_alias(self) -> bool:
        return self.type == SymbolType.TYPE_ALIAS

    @property
    def is_global_var(self) -> bool:
        return self.type == SymbolType.GLOBAL_VAR

    @property
    def is_function(self) -> bool:
        return self.type == SymbolType.FUNCTION

    @property
    def is_exception(self) -> bool:
        return self.type == SymbolType.EXCEPTION

    @property
    def is_unknown(self) -> bool:
        return self.type == SymbolType.UNKNOWN

    def __lt__(self, other) -> bool:
        if not isinstance(other, RefSymbol):
            raise TypeError
        return self.local_id < other.local_id

    def __str__(self) -> str:
        return f"{self.name} ({self.type}) in {self.rel_path}"
