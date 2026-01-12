from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from model_lib.model_base import Entity
from pydantic import Field
from zero_3rdparty.enum_utils import StrEnum

from pkg_ext.config import Stability
from pkg_ext.models.py_symbols import SymbolType


class ParamKind(StrEnum):
    POSITIONAL_ONLY = "positional_only"
    POSITIONAL_OR_KEYWORD = "positional_or_keyword"
    VAR_POSITIONAL = "var_positional"
    KEYWORD_ONLY = "keyword_only"
    VAR_KEYWORD = "var_keyword"


class ParamDefault(Entity):
    value_repr: str
    is_factory: bool = False


class FuncParamInfo(Entity):
    name: str
    kind: ParamKind
    type_annotation: str | None = None
    default: ParamDefault | None = None


class CallableSignature(Entity):
    parameters: list[FuncParamInfo] = Field(default_factory=list)
    return_annotation: str | None = None


class ClassFieldInfo(Entity):
    name: str
    type_annotation: str | None = None
    default: ParamDefault | None = None
    is_class_var: bool = False
    is_computed: bool = False
    description: str | None = None
    deprecated: str | None = None
    env_vars: list[str] | None = None


class SymbolDumpBase(Entity):
    name: str
    module_path: str
    docstring: str = ""
    stability: Stability | None = None
    since_version: str | None = None


class FunctionDump(SymbolDumpBase):
    type: Literal[SymbolType.FUNCTION] = SymbolType.FUNCTION
    signature: CallableSignature


class ClassDump(SymbolDumpBase):
    type: Literal[SymbolType.CLASS] = SymbolType.CLASS
    direct_bases: list[str] = Field(default_factory=list)
    init_signature: CallableSignature | None = None
    fields: list[ClassFieldInfo] | None = None


class ExceptionDump(SymbolDumpBase):
    type: Literal[SymbolType.EXCEPTION] = SymbolType.EXCEPTION
    direct_bases: list[str] = Field(default_factory=list)
    init_signature: CallableSignature | None = None


class TypeAliasDump(SymbolDumpBase):
    type: Literal[SymbolType.TYPE_ALIAS] = SymbolType.TYPE_ALIAS
    alias_target: str


class GlobalVarDump(SymbolDumpBase):
    type: Literal[SymbolType.GLOBAL_VAR] = SymbolType.GLOBAL_VAR
    annotation: str | None = None
    value_repr: str | None = None


SymbolDump = Annotated[
    FunctionDump | ClassDump | ExceptionDump | TypeAliasDump | GlobalVarDump,
    Field(discriminator="type"),
]


class GroupDump(Entity):
    name: str
    stability: Stability = Stability.ga
    symbols: list[SymbolDump] = Field(default_factory=list)


class PublicApiDump(Entity):
    pkg_import_name: str
    version: str
    groups: list[GroupDump] = Field(default_factory=list)
    dumped_at: datetime
