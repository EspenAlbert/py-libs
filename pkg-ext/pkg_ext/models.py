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
    Iterable,
    Self,
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
from zero_3rdparty.object_name import as_name

from pkg_ext.errors import (
    InvalidGroupSelectionError,
    LocateError,
    NoPublicGroupMatch,
)
from pkg_ext.gen_changelog import (
    ChangelogAction,
    ChangelogActionType,
    ChangelogDetailsT,
    CommitFix,
    GroupModulePath,
    OldNameNewName,
    dump_changelog_actions,
    parse_changelog_actions,
)
from pkg_ext.git_state import GitChanges
from pkg_ext.settings import PkgSettings


def ref_id_format(original: str):
    if "." not in original:
        raise ValueError(
            f"A ref_id must use the form parent.child:function module format, got: {original}"
        )
    return original


def as_module_path(rel_path: str) -> str:
    return rel_path.removesuffix(".py").replace("/", ".")


SymbolRefId: TypeAlias = Annotated[str, AfterValidator(ref_id_format)]


def ref_id_module(ref_id: SymbolRefId) -> str:
    return ref_id.rsplit(".", maxsplit=1)[0]


def ref_id_name(ref_id: SymbolRefId) -> str:
    return ref_id.rsplit(".", maxsplit=1)[-1]


def ref_id(rel_path: str, symbol_name: str) -> SymbolRefId:
    """Generate a pydoc.locate(ref_id) compatible id."""
    return f"{as_module_path(rel_path)}.{symbol_name}"


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

    @property
    def exist_in_code(self) -> bool:
        return self.type in {RefStateType.EXPOSED, RefStateType.DEPRECATED}


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

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, RefStateWithSymbol):
            return False
        return str(self.symbol) == str(value.symbol)

    def __hash__(self) -> int:
        return hash(str(self.symbol))


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
    owned_refs: set[SymbolRefId] = Field(default_factory=set)
    owned_modules: set[str] = Field(default_factory=set)

    @property
    def is_root(self) -> bool:
        return self.name == self.ROOT_GROUP_NAME

    @property
    def sorted_refs(self) -> list[str]:
        return sorted(self.owned_refs)

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
            groups_dumped = []
            for group in self_.groups:
                group_dict = group.model_dump(exclude={"owned_refs", "owned_modules"})
                if owned_modules := sorted(group.owned_modules):
                    group_dict["owned_modules"] = owned_modules
                if owned_refs := sorted(group.owned_refs):
                    group_dict["owned_refs"] = owned_refs
                groups_dumped.append(group_dict)
            self_dict = self_.model_dump(exclude={"storage_path", "groups"})
            self_dict["groups"] = groups_dumped
            yaml_text = dump(self_dict, "yaml")
            yaml_text = f"# generated by pkg-ext, never edit\n{yaml_text}"
            file_utils.ensure_parents_write_text(storage_path, yaml_text)

    return wrapper  # type: ignore


_INVALID_SYMBOL_NAME = "not-allowed"


class PublicGroups(Entity):
    groups: list[PublicGroup] = Field(default_factory=_default_public_groups)
    storage_path: Path | None = None

    @property
    def name_to_group(self) -> dict[str, PublicGroup]:
        return {group.name: group for group in self.groups}

    @property
    def groups_no_root(self) -> list[PublicGroup]:
        return sorted(group for group in self.groups if not group.is_root)

    @property
    def root_group(self) -> PublicGroup:
        root = next((group for group in self.groups if group.is_root), None)
        assert root, "root group not found"
        return root

    def matching_group(self, ref: RefSymbol) -> PublicGroup:
        if match_by_module := [
            group for group in self.groups if ref.module_path in group.owned_modules
        ]:
            assert len(match_by_module) == 1, (
                f"Expected exactly one matching group for {ref.name} in {ref.module_path}, got {len(match_by_module)}"
            )
            return match_by_module[0]
        raise NoPublicGroupMatch(
            f"No public group found for symbol {ref.name} in module {ref.module_path}"
        )

    def matching_group_by_module_path(self, module_path: str) -> PublicGroup:
        if match_by_module := [
            group for group in self.groups if module_path in group.owned_modules
        ]:
            assert len(match_by_module) == 1, (
                f"Expected exactly one matching group for module {module_path}, got {len(match_by_module)}: {match_by_module}"
            )
            return match_by_module[0]
        raise NoPublicGroupMatch(f"No public group found for module {module_path}")

    def _get_or_create_group(self, name: str) -> PublicGroup:
        group = self.name_to_group.get(name)
        if not group:
            group = PublicGroup(name=name)
            self.groups.append(group)
        return group

    @ensure_disk_path_updated
    def add_module(self, group_name: str, module_path: str) -> PublicGroup:
        group = self._get_or_create_group(group_name)
        try:
            existing = self.matching_group_by_module_path(module_path)
            if existing.name != group.name:
                raise InvalidGroupSelectionError(
                    reason=f"existing_group: {existing.name} matched for module {module_path} selected for {group_name}"
                )
            return existing
        except NoPublicGroupMatch:
            group.owned_modules.add(module_path)
            return group

    @ensure_disk_path_updated
    def add_ref(self, ref: RefSymbol, group_name: str) -> PublicGroup:
        group = self._get_or_create_group(group_name)
        try:
            matching_group = self.matching_group(ref)
            if matching_group.name != group_name:
                raise InvalidGroupSelectionError(
                    reason=f"existing_group: {matching_group.name} matched for {ref.local_id}"
                )
            group.owned_refs.add(ref.local_id)
            group.owned_modules.add(ref.module_path)
        except NoPublicGroupMatch:
            group.owned_refs.add(ref.local_id)
            group.owned_modules.add(ref.module_path)
        return group


class PkgCodeState(Entity):
    """Currently, we don't allow any shared names. E.g., mod1.Name1, mod2.Name2, Name1 != Name2"""

    pkg_import_name: str
    import_id_refs: dict[str, RefSymbol]
    files: list[PkgSrcFile | PkgTestFile]

    def _add_transitive_dependencies(self) -> None:
        """Add dependencies based on local imports."""
        while True:
            new_dependencies = False
            for file in self.files:
                for other_file in self.files:
                    if file == other_file or other_file in file.dependencies:
                        continue
                    if file._depend_from_import(other_file):
                        file.dependencies.add(other_file)
                        new_dependencies = True
            if not new_dependencies:
                break

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
        if not self.import_id_refs:
            raise ValueError("No code state found")
        self._add_transitive_dependencies()
        self.files = sorted(self.files)
        return self

    def ref_symbol(self, name: str) -> RefSymbol:
        if ref_state := self.named_refs.get(name):
            return ref_state.symbol
        raise ValueError(f"symbol not found: {name}")

    @property
    def named_refs(self) -> dict[str, RefStateWithSymbol]:
        return {
            ref.name: RefStateWithSymbol(name=ref.name, symbol=ref)
            for ref in self.import_id_refs.values()
        }

    def lookup(self, ref: RefSymbol) -> Any:
        full_reference_id = ref.full_id(self.pkg_import_name)
        py_any = locate(full_reference_id)
        if py_any is None:
            raise LocateError(full_reference_id)
        return py_any

    def as_local_ref(self, any: Any) -> RefSymbol | None:
        import_id = as_name(any)
        pkg_prefix = f"{self.pkg_import_name}."
        if import_id.startswith(pkg_prefix):
            name = ref_id_name(import_id)
            if len(name) == 1:  # most likely a TypeAlias, like T, which are not stored
                return None
            return self.import_id_refs[import_id]

    def sort_refs(self, refs: Iterable[SymbolRefId]) -> list[SymbolRefId]:
        def lookup_in_file(ref: SymbolRefId) -> tuple[int, str]:
            module_name = ref_id_module(ref)
            ref_name = ref_id_name(ref)
            for i, file in enumerate(self.files):
                for symbol in file.iterate_ref_symbols():
                    if (
                        symbol.name == ref_name
                        and file.module_local_path == module_name
                    ):
                        return i, ref_name
            raise ValueError(f"ref not found in any file: {ref}")

        return sorted(refs, key=lookup_in_file)

    def sort_rel_paths_by_dependecy_order(
        self, paths: Iterable[str], reverse: bool = True
    ) -> list[str]:
        """assume a.py:
        from my_pkg.b import b
        def a():
            b()
        Then the order will be b, a
        If reverse=True, a, b # reversed dependency order
        """

        def key_in_files(rel_path: str) -> int:
            for i, file in enumerate(self.files):
                if file.relative_path == rel_path:
                    return i
            raise ValueError(f"rel_path not found in any file: {rel_path}")

        return sorted(paths, key=key_in_files, reverse=reverse)


class PkgExtState(Entity):
    repo_root: DirectoryPath
    changelog_dir: DirectoryPath
    pkg_path: DirectoryPath
    refs: dict[str, RefState] = Field(
        default_factory=dict,
        description="Mapping of reference names to their states. Use with caution, inferred by changelog_dir entries.",
    )
    groups: PublicGroups = Field(
        default_factory=PublicGroups,
        description="Use with caution, inferred by changelog_dir entries.",
    )
    ignored_shas: set[str] = Field(
        default_factory=set,
        description="Fix commits not included in the changelog",
    )
    included_shas: set[str] = Field(
        default_factory=set,
        description="Fix commits included in the changelog",
    )

    @classmethod
    def parse(
        cls, settings: PkgSettings, code_state: PkgCodeState | None = None
    ) -> Self:
        changelog_path = settings.changelog_path
        changelog_path.mkdir(parents=True, exist_ok=True)
        actions = parse_changelog_actions(changelog_path)
        groups = PublicGroups(storage_path=settings.public_groups_path)
        ref_state = cls(
            repo_root=settings.repo_root,
            changelog_dir=changelog_path,
            pkg_path=settings.pkg_directory,
            groups=groups,
        )
        for action in actions:
            ref_state.update_state(action)
        if code_state:
            for name, ref in ref_state.refs.items():
                if ref.exist_in_code:
                    with suppress(
                        ValueError
                    ):  # can happen if the name from changelog has been removed
                        ref_symbol = code_state.ref_symbol(name)
                        group = groups.matching_group(ref_symbol)
                        groups.add_ref(ref_symbol, group.name)
        return ref_state

    def sha_processed(self, sha: str) -> bool:
        return sha in self.ignored_shas or sha in self.included_shas

    def current_state(self, ref_name: str) -> RefState:
        if state := self.refs.get(ref_name):
            return state
        self.refs[ref_name] = state = RefState(name=ref_name)
        return state

    def update_state(self, action: ChangelogAction) -> None:
        """Update the state of a reference based on a changelog action."""
        match action:
            case ChangelogAction(action=ChangelogActionType.EXPOSE):
                state = self.current_state(action.name)
                state.type = RefStateType.EXPOSED
            case ChangelogAction(action=ChangelogActionType.HIDE):
                state = self.current_state(action.name)
                state.type = RefStateType.HIDDEN
            case ChangelogAction(action=ChangelogActionType.DEPRECATE):
                state = self.current_state(action.name)
                state.type = RefStateType.DEPRECATED
            case ChangelogAction(action=ChangelogActionType.DELETE):
                state = self.current_state(action.name)
                state.type = RefStateType.DELETED
            case ChangelogAction(
                action=ChangelogActionType.RENAME_AND_DELETE,
                details=OldNameNewName(old_name=old_name),
            ):
                state = self.current_state(action.name)
                old_state = self.current_state(old_name)
                old_state.type = RefStateType.DELETED
                state.type = RefStateType.EXPOSED
            case ChangelogAction(
                name=group_name,
                action=ChangelogActionType.GROUP_MODULE,
                details=GroupModulePath(module_path=module_path),
            ):
                self.groups.add_module(group_name, module_path)
            case ChangelogAction(
                action=ChangelogActionType.FIX,
                details=CommitFix(short_sha=sha, ignored=ignored),
            ):
                shas = self.ignored_shas if ignored else self.included_shas
                shas.add(sha)

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

    def is_pkg_relative(self, rel_path: str) -> bool:
        pkg_rel_path = self.pkg_path.relative_to(self.repo_root)
        return rel_path.startswith(str(pkg_rel_path))

    def full_path(self, rel_path_repo: str) -> Path:
        return self.repo_root / rel_path_repo


RefAddCallback: TypeAlias = Callable[[RefSymbol], ChangelogAction | None]


@dataclass
class pkg_ctx:
    settings: PkgSettings
    tool_state: PkgExtState
    code_state: PkgCodeState
    git_changes: GitChanges | None = None
    ref_add_callback: list[RefAddCallback] = field(default_factory=list)

    _actions: list[ChangelogAction] = field(default_factory=list, init=False)

    def add_changelog_action(self, action: ChangelogAction) -> list[ChangelogAction]:
        actions = [action]
        name = action.name
        if action.action == ChangelogActionType.EXPOSE:
            ref = self.code_state.ref_symbol(name)
            for call in self.ref_add_callback:
                if extra_action := call(ref):
                    actions.insert(0, extra_action)
        self._actions.extend(actions)
        self.tool_state.add_changelog_actions(actions)
        return actions

    def add_action(
        self,
        name: str,
        type: ChangelogActionType,
        details: ChangelogDetailsT | None = None,
    ) -> list[ChangelogAction]:
        action = ChangelogAction(name=name, action=type, details=details)
        return self.add_changelog_action(action)

    def __enter__(self) -> pkg_ctx:
        return self

    def __exit__(self, *_):
        if actions := self._actions:
            dump_changelog_actions(self.tool_state.changelog_dir, actions)
