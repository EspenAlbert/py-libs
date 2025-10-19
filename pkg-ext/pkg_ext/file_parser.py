import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from zero_3rdparty.iter_utils import flat_map

from pkg_ext.models import (
    PkgSrcFile,
    PkgTestFile,
    RefSymbol,
    is_dunder_file,
    is_test_file,
    ref_id,
)

logger = logging.getLogger(__name__)


@dataclass
class SymbolParser(ast.NodeTransformer):
    pkg_import_name: str
    local_imports: set[str] = field(init=False, default_factory=set)
    type_aliases: list[str] = field(init=False, default_factory=list)
    global_vars: list[str] = field(init=False, default_factory=list)
    functions: list[str] = field(init=False, default_factory=list)
    classes: list[str] = field(init=False, default_factory=list)
    exceptions: list[str] = field(init=False, default_factory=list)

    def name_is_imported(self, name: str) -> bool:
        """Check if the name is imported from the package."""
        return any(ref.endswith(f":{name}") for ref in self.local_imports)

    def visit_Name(self, node: ast.Name) -> ast.AST:
        """TODO: revisit this logic
        For type aliases: Check for TypeAlias annotations or assignments to typing constructs
        For global variables: Track the context (module-level vs local scope)
        Use sets instead of lists to avoid duplicates
        """
        node_name = node.id
        if self.name_is_imported(node_name):
            return node
        if len(node_name) == 1:
            return node
        if node_name.isupper():
            self.global_vars.append(node.id)
        elif node.id.endswith("T"):
            self.type_aliases.append(node.id)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        """TODO: Consider parsing function with generic_visit in case I want to look for raise statements and inspect signature."""
        if node.name.startswith("_"):
            # Skip private functions
            return node
        self.functions.append(node.name)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        if node.name.startswith("_"):
            # Skip private classes
            return node
        # TODO: Consider importing actual cls and using __mro__ for more robust exception detection
        # Consider self.generic_visit
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
        if node.level > 0:
            logger.info("is this a relative import? Might need to support that too")
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
    is_generated: Callable[[str], bool] | None = None,
) -> PkgSrcFile | PkgTestFile | None:
    if is_dunder_file(path):
        return None
    py_script = path.read_text()
    if is_generated and is_generated(py_script):
        return None
    try:
        tree = ast.parse(py_script, type_comments=True)
    except SyntaxError as e:
        logger.warning(f"Syntax error while parsing {path}: {e}")
        return None
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


def parse_code_symbols(
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


__all__ = [
    "parse_code_symbols",
    "parse_symbols",
]
