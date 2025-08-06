import ast
from dataclasses import dataclass, field
from pathlib import Path

from pkg_ext.models import PkgSrcFile, PkgTestFile, is_dunder_file, is_test_file, ref_id


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
        node_name = node.id
        if self.name_is_imported(node_name):
            return node
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
