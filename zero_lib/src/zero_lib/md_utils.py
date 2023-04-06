from typing import Iterable

from zero_lib.error import BaseError


class MdTableColsError(BaseError):
    def __init__(self, cols: list[str]):
        self.cols = cols


def table_header_lines(cols: Iterable[str]) -> list[str]:
    # in case only an iterator
    cols = list(cols)
    if not cols or cols[0].startswith("#"):
        raise MdTableColsError(cols)
    return [
        " | ".join(cols),
        " | ".join("---" for _ in range(len(cols))),
    ]
