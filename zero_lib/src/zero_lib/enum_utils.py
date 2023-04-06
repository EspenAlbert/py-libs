from enum import Enum


class StrEnum(str, Enum):
    """Needed to avoid the enum repr: "<_Status.STARTED: 'STARTED'>".

    Will become unnecessary in python3.11:
    https://docs.python.org/3.11/library/enum.html#enum.StrEnum
    """

    def __repr__(self) -> str:
        return str.__repr__(self)

    def __str__(self) -> str:
        return str.__str__(self)
