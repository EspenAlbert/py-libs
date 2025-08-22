from pathlib import Path

from pycobertura import Cobertura
from pycobertura.cobertura import Line
from pycobertura.filesystem import filesystem_factory


def is_covered(coverage_path: Path, module_path: str, line_number: int) -> bool:
    """module_path: format; pkg-ext/pkg_ext/ref_processor.py"""
    report = Cobertura(coverage_path)
    file_lines = dict(report.missed_lines(module_path))
    return line_number not in file_lines


_zero_index_line = Line(0, "", None, None)


def cov_lines(repo_path: Path, coverage_path: Path, module_path: str) -> list[Line]:
    """Returns lines where you can use the same line_nr as index.
    Line:
      - number
      - source
      - status
      - reason
    """
    file_system = filesystem_factory(repo_path)
    report = Cobertura(coverage_path, filesystem=file_system)
    return [_zero_index_line] + report.file_source(module_path)  # type: ignore
