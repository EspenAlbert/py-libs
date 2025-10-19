from __future__ import annotations

from pydoc import locate
from typing import Any, Iterable

from model_lib.model_base import Entity
from pydantic import model_validator
from zero_3rdparty.iter_utils import group_by_once
from zero_3rdparty.object_name import as_name

from pkg_ext.errors import LocateError, RefSymbolNotInCodeError

from .py_files import PkgSrcFile, PkgTestFile
from .py_symbols import RefSymbol
from .ref_state import RefStateWithSymbol
from .types import SymbolRefId, ref_id_module, ref_id_name


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
        raise RefSymbolNotInCodeError(name)

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
