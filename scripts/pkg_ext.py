from __future__ import annotations

import ast
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from functools import total_ordering
from os import getenv
from pathlib import Path
from pydoc import locate
from typing import ClassVar, Iterable, Literal

import typer
from ask_shell._run import run_and_wait
from ask_shell.interactive import (
    ChoiceTyped,
    confirm,
    select_list_choice,
    select_list_multiple_choices,
)
from ask_shell.typer_command import configure_logging
from model_lib import utc_datetime
from model_lib.model_base import Entity
from model_lib.serialize import dump
from model_lib.serialize.parse import parse_model
from pydantic import DirectoryPath, Field, ValidationError, model_validator
from typer import Typer
from zero_3rdparty.datetime_utils import (
    date_filename_with_seconds,
    parse_date_filename_with_seconds,
    utc_now,
)
from zero_3rdparty.enum_utils import StrEnum
from zero_3rdparty.file_utils import iter_paths_and_relative
from zero_3rdparty.iter_utils import flat_map, group_by_once

app = Typer(name="pkg-ext", help="Generate public API for a package and more!")
logger = logging.getLogger(__name__)
ACTION_FILE_SPLIT = "---\n"


def ref_id(rel_path: str, symbol_name: str) -> str:
    """Generate a unique reference ID based on the relative path and symbol name."""
    return f"{rel_path.removesuffix('.py')}:{symbol_name}"


def is_test_file(path: Path) -> bool:
    return (
        path.name.startswith("test_")
        or path.name.endswith("_test.py")
        or path.name == "conftest.py"
    )


def is_dunder_file(path: Path) -> bool:
    return path.stem.startswith("__") and path.stem.endswith("__")


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
        return any(ref.startswith(other_import_name) for ref in self.local_imports)

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


class PkgSrcFile(PkgFileBase):
    type_aliases: list[str] = Field(default_factory=list)
    global_vars: list[str] = Field(default_factory=list)
    functions: list[str] = Field(default_factory=list)
    classes: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_not_a_test(self):
        if is_test_file(self.path):
            raise ValueError(f"File {self.path} is a test file, not a package file.")
        if is_dunder_file(self.path):
            raise ValueError(f"File {self.path} is a a package file.")
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
        return f"{self.rel_path.removesuffix('.py')}:{self.name}"

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


@dataclass
class SymbolParser(ast.NodeTransformer):
    pkg_import_name: str
    local_imports: set[str] = field(init=False, default_factory=set)
    type_aliases: list[str] = field(init=False, default_factory=list)
    global_vars: list[str] = field(init=False, default_factory=list)
    functions: list[str] = field(init=False, default_factory=list)
    classes: list[str] = field(init=False, default_factory=list)
    exceptions: list[str] = field(init=False, default_factory=list)

    def visit_Name(self, node: ast.Name) -> ast.AST:
        node_name = node.id
        if node_name.isupper():
            self.global_vars.append(node.id)
        elif node.id.endswith("T"):
            self.type_aliases.append(node.id)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        if node.name.startswith("_"):
            # Skip private functions
            return node
        self.functions.append(node.name)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        if node.name.startswith("_"):
            # Skip private classes
            return node
        bases = {base.id for base in node.bases if isinstance(base, ast.Name)}
        if "Exception" in bases or "BaseException" in bases:
            self.exceptions.append(node.name)
        else:
            self.classes.append(node.name)
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AnnAssign:
        if isinstance(node.target, ast.Name):
            if node.target.id.isupper():
                self.global_vars.append(node.target.id)
            elif node.target.id.endswith("T"):
                self.type_aliases.append(node.target.id)
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom:
        module_name = node.module or ""
        if not module_name.startswith(self.pkg_import_name):
            return node
        for name in node.names:
            if name.name.startswith("_"):
                # Skip private imports
                continue
            ref_id_value = ref_id(module_name, name.name)
            self.local_imports.add(ref_id_value)
        return node


def parse_symbols(
    path: Path,
    rel_path: str,
    pkg_import_name: str,
) -> PkgSrcFile | PkgTestFile | None:
    if is_dunder_file(path):
        return None
    py_script = path.read_text()
    tree = ast.parse(py_script, type_comments=True)
    parser = SymbolParser(pkg_import_name=pkg_import_name)
    parser.visit(tree)
    if is_test_file(path):
        return PkgTestFile(
            path=path,
            relative_path=rel_path,
            local_imports=parser.local_imports,
            pkg_import_name=pkg_import_name,
        )
    return PkgSrcFile(
        path=path,
        relative_path=rel_path,
        pkg_import_name=pkg_import_name,
        local_imports=parser.local_imports,
        type_aliases=parser.type_aliases,
        global_vars=parser.global_vars,
        functions=parser.functions,
        classes=parser.classes,
        exceptions=parser.exceptions,
    )


class ChangelogActionType(StrEnum):
    EXPOSE = "expose"
    HIDE = "hide"
    FIX = "fix"
    DEPRECATE = "deprecate"
    DELETE = "delete"
    RENAME_AND_DELETE = "rename_and_delete"
    BREAKING_CHANGE = "breaking_change"  # todo: Possibly support signature changes
    ADDITIONAL_CHANGE = "additional_change"  # todo: Possibly support signature changes


def current_user() -> str:
    return (
        ChangelogAction.DEFAULT_AUTHOR
    )  # todo: read from git config or environment variable


class OldNameNewName(Entity):
    old_name: str
    new_name: str
    type: Literal["old_name_new_name"] = "old_name_new_name"


ChangelogDetailsT = OldNameNewName | str | None


@total_ordering
class ChangelogAction(Entity):
    name: str = Field(..., description="Symbol name")
    action: ChangelogActionType = Field(
        ...,
        description=f"Action to take with the public reference, one of {list(ChangelogActionType)}",
    )
    ts: utc_datetime = Field(
        default_factory=utc_now, description="Timestamp of the action"
    )

    DEFAULT_AUTHOR: ClassVar[str] = "UNSET"
    author: str = Field(
        default_factory=current_user,
        description="Author of the public reference action",
    )
    details: ChangelogDetailsT = Field(
        default=None,
        description="Details of the action, for example details on changes",
    )
    pr: str | None = Field(
        default="",
        description="Pull request number, set from default branch before releasing after merge.",
    )

    def __lt__(self, other) -> bool:
        if not isinstance(other, ChangelogAction):
            raise TypeError
        return (self.ts, self.name) < (other.ts, other.name)

    @property
    def filename(self) -> str:
        """Generate a filename for the changelog action based on its timestamp."""
        return f"{date_filename_with_seconds(self.ts, force_utc=True)}.yaml"

    @property
    def file_content(self) -> str:
        ignored_falsy = self.model_dump(
            exclude_unset=True, exclude_none=True, exclude_defaults=True, exclude={"ts"}
        )
        return dump(ignored_falsy, format="yaml")


def parse_changelog_actions(changelog_dir_path: Path) -> list[ChangelogAction]:
    actions: list[ChangelogAction] = []
    for path in changelog_dir_path.glob("*.yaml"):
        actions.extend(parse_changelog_action(path))
    return sorted(actions)


def parse_changelog_action(path: Path) -> list[ChangelogAction]:
    ts = parse_date_filename_with_seconds(path.stem)
    return [
        parse_model(
            action_raw,
            t=ChangelogAction,
            extra_kwargs={"ts": ts},
            format="yaml",
        )
        for action_raw in path.read_text().split(ACTION_FILE_SPLIT)
        if action_raw.strip()
    ]


def dump_changelog_action(path: Path, action: ChangelogAction) -> None:
    if not path.exists():
        path.write_text(action.file_content)
        return
    existing_actions = parse_changelog_action(path)
    existing_actions.append(action)
    existing_actions.sort()
    yaml_content = ACTION_FILE_SPLIT.join(
        action.file_content for action in existing_actions
    )
    path.write_text(yaml_content)


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


class PkgRefState(Entity):
    refs: dict[str, RefState] = Field(
        default_factory=dict, description="Mapping of reference names to their states"
    )
    changelog_dir: DirectoryPath
    pkg_path: DirectoryPath

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

    def removed_refs(
        self, active_refs: dict[str, RefStateWithSymbol]
    ) -> dict[str, str]:
        return {
            ref_name: f"{state.type.value} -> removed"
            for ref_name, state in self.refs.items()
            if state.type in {RefStateType.EXPOSED, RefStateType.DEPRECATED}
            and ref_name not in active_refs
        }

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

    def add_action(self, action: ChangelogAction) -> None:
        self.update_state(action)
        path = self.changelog_dir / action.filename
        dump_changelog_action(path, action)

    def dump_to_init(self, active_refs: dict[str, RefState]) -> None:
        raise NotImplementedError


def create_ref_state(pkg_path: Path, changelog_dir: Path) -> PkgRefState:
    """Create a mapping of reference names to their states based on changelog actions."""
    actions = parse_changelog_actions(changelog_dir)
    ref_state = PkgRefState(changelog_dir=changelog_dir, pkg_path=pkg_path)
    for action in actions:
        ref_state.update_state(action)
    return ref_state


def get_editor() -> str:
    return getenv("EDITOR", "code")


@app.command()
def generate_api(
    pkg_path_str: str = typer.Argument(
        ...,
        help="Path to the package directory, expecting pkg_path/__init__.py to exist",
    ),
):
    pkg_path = Path(pkg_path_str).resolve()
    assert pkg_path.is_dir(), f"Expected a directory, got {pkg_path}"
    init_file = pkg_path / "__init__.py"
    assert init_file.is_file(), f"Expected {init_file} to exist"
    pkg_py_files = list(iter_paths_and_relative(pkg_path, "*.py", only_files=True))
    pkg_import_name = pkg_path.name
    parsed_files = sorted(
        parsed
        for path, rel_path in pkg_py_files
        if (parsed := parse_symbols(path, rel_path, pkg_import_name))
    )
    import_id_symbols = create_refs(parsed_files, pkg_import_name)
    active_states = named_refs(import_id_symbols)
    changelog_dir_path = init_file.parent.parent / ".changelog"
    changelog_dir_path.mkdir(parents=True, exist_ok=True)
    state = create_ref_state(pkg_path, changelog_dir_path)
    handle_removed_refs(state, active_states)
    # Todo: Handle changed refs by inspecting signatures
    handle_added_refs(state, active_states)


def named_refs(import_id_refs: dict[str, RefSymbol]) -> dict[str, RefStateWithSymbol]:
    active_refs = group_by_once(import_id_refs.values(), key=lambda ref: ref.name)
    duplicated_refs = [
        f"duplicated refs for {name}: " + ", ".join(str(ref) for ref in duplicated_refs)
        for name, duplicated_refs in active_refs.items()
        if len(duplicated_refs) > 1
    ]
    duplicated_refs_lines = "\n".join(duplicated_refs)
    assert not duplicated_refs, f"Found duplicated references: {duplicated_refs_lines}"
    return {
        ref.name: RefStateWithSymbol(name=ref.name, symbol=ref)
        for ref in import_id_refs.values()
    }


def handle_removed_refs(
    pkg_state: PkgRefState, active_refs: dict[str, RefStateWithSymbol]
) -> None:
    removed_refs = pkg_state.removed_refs(active_refs)
    if not removed_refs:
        logger.info("No removed references found in the package")
        return
    renames: list[str] = select_list_multiple_choices(
        "Select references thas has been renamed (if any):",
        choices=ChoiceTyped.from_descriptions(removed_refs),
    )
    used_active: set[str] = set()
    if renames:
        for ref_name in renames:
            rename_choices = [
                state.as_choice()
                for name, state in active_refs.items()
                if name not in used_active
            ]
            new_state = select_list_choice(
                f"Select new name for the reference {ref_name}",
                choices=rename_choices,
            )
            if confirm(
                f"Rename {ref_name} to {new_state}, should we create an alias to avoid a breaking change?",
                default=False,
            ):
                raise NotImplementedError("Alias creation is not implemented yet")
            # Any DELETE is a breaking change? Or also add that entry?
            pkg_state.add_action(
                ChangelogAction(
                    name=new_state,
                    action=ChangelogActionType.RENAME_AND_DELETE,
                    details=OldNameNewName(old_name=ref_name, new_name=new_state),
                )
            )
            removed_refs.pop(ref_name, None)
    assert confirm(
        "Confirm deleting remaining refs: " + ", ".join(removed_refs.keys()),
    ), (
        f"Old references {', '.join(removed_refs.keys())} were not confirmed for deletion"
    )
    for ref_name, reason in removed_refs.items():
        pkg_state.add_action(
            ChangelogAction(
                name=ref_name,
                action=ChangelogActionType.DELETE,
                details=reason,
            )
        )


def handle_added_refs(
    pkg_state: PkgRefState, active_refs: dict[str, RefStateWithSymbol]
) -> None:
    added_refs = pkg_state.added_refs(active_refs)
    if not added_refs:
        logger.info("No new references found in the package")
        return

    def group_by_file(state: RefStateWithSymbol) -> str:
        return state.symbol.rel_path

    file_added_refs = group_by_once(added_refs.values(), key=group_by_file)
    for file_name, file_states in file_added_refs.items():
        run_and_wait(f"{get_editor()} {pkg_state.pkg_path / file_name}")
        choices = {
            state.name: state.symbol.as_choice(checked=False) for state in file_states
        }
        expose_refs = select_list_multiple_choices(
            f"Select references to expose from {file_name} (if any):",
            choices=list(choices.values()),
            default=[],
        )
        for state in file_states:
            action = (
                ChangelogActionType.EXPOSE
                if state.name in expose_refs
                else ChangelogActionType.HIDE
            )
            pkg_state.add_action(
                ChangelogAction(
                    name=state.name, action=action, details=f"Created in {file_name}"
                )
            )


def create_refs(
    parsed_files: list[PkgSrcFile | PkgTestFile], pkg_import_name: str
) -> dict[str, RefSymbol]:
    refs = {
        symbol.full_id(pkg_import_name): symbol
        for symbol in flat_map(file.iterate_ref_symbols() for file in parsed_files)
    }
    globals_added: set[str] = set()
    for symbol in list(refs.values()):
        global_import = f"{pkg_import_name}:{symbol.name}"
        globals_added.add(global_import)
        refs[global_import] = symbol

    for file in parsed_files:
        for ref_usage in file.iterate_usage_ids():
            ref = refs.get(ref_usage)
            if not ref:
                if "conftest" in ref_usage and isinstance(file, PkgTestFile):
                    logger.debug(
                        f"Skipping conftest usage {ref_usage} in {file.relative_path}"
                    )
                    continue
                logger.warning(f"Reference {ref_usage} not found in parsed files")
                continue
            match file:
                case PkgTestFile():
                    ref.test_usages.append(file.relative_path)
                case PkgSrcFile():
                    ref.src_usages.append(file.relative_path)
    for global_import in globals_added:
        refs.pop(global_import, None)
    return refs


def main():
    configure_logging(app)
    app()


if __name__ == "__main__":
    main()
