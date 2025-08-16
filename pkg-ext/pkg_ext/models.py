from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field
from functools import total_ordering, wraps
from pathlib import Path
from pydoc import locate
from typing import (
    Annotated,
    Any,
    Callable,
    ClassVar,
    ContextManager,
    Iterable,
    Protocol,
    TypeAlias,
    TypeVar,
)

from ask_shell._internal.interactive import ChoiceTyped
from model_lib.model_base import Entity
from model_lib.serialize import dump
from pydantic import (
    AfterValidator,
    DirectoryPath,
    Field,
    ValidationError,
    model_validator,
)
from zero_3rdparty import file_utils
from zero_3rdparty.enum_utils import StrEnum
from zero_3rdparty.iter_utils import group_by_once

from pkg_ext.errors import (
    InvalidGroupSelectionError,
    NoPublicGroupMatch,
    PublicGroupAlreadyExist,
)
from pkg_ext.gen_changelog import (
    ChangelogAction,
    ChangelogActionType,
    ChangelogDetailsT,
    OldNameNewName,
    dump_changelog_actions,
)


def ref_id_format(original: str):
    if ":" not in original:
        raise ValueError(
            f"A ref_id must use the form parent.child:function module format, got: {original}"
        )
    return original


def as_module_path(rel_path: str) -> str:
    return rel_path.removesuffix(".py").replace("/", ".")


SymbolRefId: TypeAlias = Annotated[str, AfterValidator(ref_id_format)]


def ref_id_module(ref_id: SymbolRefId) -> str:
    return ref_id.split(":")[0]


def ref_id(rel_path: str, symbol_name: str) -> SymbolRefId:
    """Generate a unique reference ID based on the relative path and symbol name."""
    return f"{as_module_path(rel_path)}:{symbol_name}"


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


def is_root_identifier(value: str):
    if value.isidentifier():
        return value
    raise ValueError(
        f"invalid python identifier: {value}, must not use . and be valid module name"
    )


PyIdentifier: TypeAlias = Annotated[str, AfterValidator(is_root_identifier)]


@total_ordering
class PublicGroup(Entity):
    ROOT_GROUP_NAME: ClassVar[str] = "__ROOT__"
    name: PyIdentifier
    owned_refs: list[SymbolRefId] = Field(default_factory=list)

    @property
    def is_root(self) -> bool:
        return self.name == self.ROOT_GROUP_NAME

    @property
    def owned_modules(self) -> set[str]:
        return {ref_id_module(ref) for ref in self.owned_refs}

    def dump(self) -> dict:
        return self.model_dump()

    def __lt__(self, other) -> bool:
        if not isinstance(other, PublicGroup):
            raise TypeError
        return self.name < other.name


def _default_public_groups() -> list[PublicGroup]:
    return [PublicGroup(name=PublicGroup.ROOT_GROUP_NAME)]


T = TypeVar("T", bound=Callable)


def ensure_disk_path_updated(func: T) -> T:
    @wraps(func)
    def wrapper(self_: PublicGroups, *args: Any, **kwargs: Any) -> Any:
        try:
            return func(self_, *args, **kwargs)
        except BaseException:
            raise
        finally:
            storage_path = self_.storage_path
            if storage_path is None:
                return
            file_ext = storage_path.suffix
            assert file_ext in (".yaml", ".yml"), (
                "Disk path must have .yaml or .yml extension"
            )
            self_.groups.sort()
            for group in self_.groups:
                group.owned_refs = sorted(set(group.owned_refs))
            self_dict = self_.model_dump(exclude={"storage_path"})
            yaml_text = dump(self_dict, "yaml")
            file_utils.ensure_parents_write_text(storage_path, yaml_text)

    return wrapper  # type: ignore


_INVALID_SYMBOL_NAME = "not-allowed"


class PublicGroups(Entity):
    STORAGE_FILENAME: ClassVar[str] = ".groups.yaml"
    groups: list[PublicGroup] = Field(default_factory=_default_public_groups)
    storage_path: Path | None = None

    @property
    def name_to_group(self) -> dict[str, PublicGroup]:
        return {group.name: group for group in self.groups}

    def matching_group(self, symbol_name: str, module_path: str) -> PublicGroup:
        if match_by_module := [
            group for group in self.groups if module_path in group.owned_modules
        ]:
            assert len(match_by_module) == 1, (
                f"Expected exactly one matching group for {symbol_name} in {module_path}, got {len(match_by_module)}"
            )
            return match_by_module[0]
        raise NoPublicGroupMatch(
            f"No public group found for symbol {symbol_name} in module {module_path}"
        )

    @ensure_disk_path_updated
    def add_group(self, group: PublicGroup) -> PublicGroup:
        if group.name in self.name_to_group:
            raise PublicGroupAlreadyExist(group.name)
        self.groups.append(group)
        return group

    @ensure_disk_path_updated
    def add_ref(self, ref: RefSymbol, group_name: str) -> PublicGroup:
        group = self.name_to_group.get(group_name)
        if not group:
            group = PublicGroup(name=group_name)
            self.add_group(group)
        try:
            matching_group = self.matching_group(ref.name, ref.module_path)
            if matching_group.name != group_name:
                raise InvalidGroupSelectionError(
                    reason=f"existing_group: {matching_group.name} matched for {ref.local_id}"
                )
            group.owned_refs.append(ref.local_id)
        except NoPublicGroupMatch:
            group.owned_refs.append(ref.local_id)
        return group


class PkgCodeState(Entity):
    """Currently, we don't allow any shared names. E.g., mod1.Name1, mod2.Name2, Name1 != Name2"""

    import_id_refs: dict[str, RefSymbol]

    @model_validator(mode="after")
    def ensure_no_duplicate_names(self):
        active_refs = group_by_once(
            self.import_id_refs.values(), key=lambda ref: ref.name
        )
        duplicated_refs = [
            f"duplicated refs for {name}: "
            + ", ".join(str(ref) for ref in duplicated_refs)
            for name, duplicated_refs in active_refs.items()
            if len(duplicated_refs) > 1
        ]
        duplicated_refs_lines = "\n".join(duplicated_refs)
        assert not duplicated_refs, (
            f"Found duplicated references: {duplicated_refs_lines}"
        )
        return self

    @property
    def named_refs(self) -> dict[str, RefStateWithSymbol]:
        return {
            ref.name: RefStateWithSymbol(name=ref.name, symbol=ref)
            for ref in self.import_id_refs.values()
        }


class AddChangelogAction(Protocol):
    def __call__(
        self,
        name: str,
        type: ChangelogActionType,
        details: ChangelogDetailsT | None = None,
    ) -> Any: ...


class PkgExtState(Entity):
    refs: dict[str, RefState] = Field(
        default_factory=dict, description="Mapping of reference names to their states"
    )
    changelog_dir: DirectoryPath
    pkg_path: DirectoryPath
    groups: PublicGroups

    def current_state(self, ref_name: str) -> RefState:
        if state := self.refs.get(ref_name):
            return state
        self.refs[ref_name] = state = RefState(name=ref_name)
        return state

    def update_state(self, action: ChangelogAction) -> None:
        """Update the state of a reference based on a changelog action."""
        state = self.current_state(action.name)
        match action.action:
            case ChangelogActionType.EXPOSE:
                state.type = RefStateType.EXPOSED
            case ChangelogActionType.HIDE:
                state.type = RefStateType.HIDDEN
            case ChangelogActionType.DEPRECATE:
                state.type = RefStateType.DEPRECATED
            case ChangelogActionType.DELETE:
                state.type = RefStateType.DELETED
            case ChangelogActionType.RENAME_AND_DELETE:
                details = action.details
                if isinstance(details, OldNameNewName):
                    old_state = self.current_state(details.old_name)
                    old_state.type = RefStateType.DELETED
                    state.type = RefStateType.EXPOSED

    def removed_refs(self, code: PkgCodeState) -> list[RefState]:
        named_refs = code.named_refs
        return [
            state
            for ref_name, state in self.refs.items()
            if state.type in {RefStateType.EXPOSED, RefStateType.DEPRECATED}
            and ref_name not in named_refs
        ]

    def added_refs(
        self, active_refs: dict[str, RefStateWithSymbol]
    ) -> dict[str, RefStateWithSymbol]:
        """Get references that were added to the package."""
        return {
            ref_name: ref_symbol
            for ref_name, ref_symbol in active_refs.items()
            if ref_name not in self.refs
            or (self.refs[ref_name].type == RefStateType.UNSET)
        }

    def add_changelog_actions(self, actions: list[ChangelogAction]) -> None:
        assert actions, "must add at least one action"
        for action in actions:
            self.update_state(action)
        action = min(actions)
        path = self.changelog_dir / action.filename
        dump_changelog_actions(path, actions)

    def is_exposed(self, ref_name: str) -> bool:
        return self.current_state(ref_name).type in {
            RefStateType.EXPOSED,
            RefStateType.DEPRECATED,
        }

    def exposed_refs(
        self, active_refs: dict[str, RefStateWithSymbol]
    ) -> dict[str, RefSymbol]:
        return {
            name: state.symbol
            for name, state in active_refs.items()
            if self.is_exposed(name)
        }

    def changelog_updater(self) -> ContextManager[AddChangelogAction]:
        return changelog_updater(self)


@dataclass
class changelog_updater:
    state: PkgExtState
    _actions: list[ChangelogAction] = field(default_factory=list)

    def add_action(
        self, name: str, type: ChangelogActionType, details: str | None = None
    ) -> ChangelogAction:
        action = ChangelogAction(name=name, action=type, details=details)
        self._actions.append(action)
        return action

    def __enter__(self) -> AddChangelogAction:
        return self.add_action

    def __exit__(self, *_):
        self.state.add_changelog_actions(self._actions)
