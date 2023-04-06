"""Why is this needed?

## Fewer lines for definition and better str()
1. Always the name of the error in the str(error)
2. No need to call super().__init__()

class MyError(Exception):
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age
        super().__init__(name, age)


instance = MyError(name="n1", age=22)
print(str(instance))('n1', 22) # <-- Reason 1
print(repr(instance)) MyError('n1', 22)


class MyError(BaseError):
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age
        # notice no call to super() <-- Reason 2


instance = MyError(name="n1", age=22)
print(str(instance)) MyError(name='n1', age=22)
print(repr(instance)) MyError(name='n1', age=22)

## Differentiate between ok/error/crash
Errors
-------
3 types:
1. ExpectedError (HTTP 4XX)
2. Crash (HTTP 5XX)
3. OK (HTTP <400), useful for raising an error to return,

To define errors subclass the BaseError class and specify:
1. code (expected/crashes)
2. optionally a msg_template
"""
from __future__ import annotations

import logging
import traceback
from asyncio import TimeoutError as AsyncTimeoutError
from concurrent.futures import TimeoutError as ConcTimeoutError
from functools import partial, singledispatch
from types import TracebackType
from typing import TYPE_CHECKING, Type, TypeAlias

from zero_lib.enum_utils import StrEnum

logger = logging.getLogger(__name__)
ExcInfo: TypeAlias = tuple[Type[BaseException], BaseException, TracebackType]


class KwargsError(Exception):
    """Used when you want you do not want to define an init for the error."""

    if TYPE_CHECKING:

        def __getattr__(self, item):
            return self.__dict__[item]

    def __init__(self, **kwargs):
        as_str = ",".join(
            f"{key}={value!r}" if isinstance(key, str) else f"{key!r}={value!r}"
            for key, value in kwargs.items()
        )
        cls_name = self.__class__.__name__
        self.__dict__.update(kwargs)
        super().__init__(f"{cls_name}({as_str})")

    def __repr__(self):
        return str(self)


class Code(StrEnum):
    OK = "OK"
    UNKNOWN = "UNKNOWN"
    INTERNAL = "INTERNAL"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    UNIMPLEMENTED = "UNIMPLEMENTED"
    TIMEOUT = "TIMEOUT"

    @classmethod
    def is_crash(cls, code: str):
        return is_crash(code)

    @classmethod
    def is_ok(cls, code: str):
        return is_ok(code)

    @classmethod
    def is_timeout(cls, code: str):
        return is_timeout(code)

    @classmethod
    def is_error(cls, code: str):
        return is_error(code)


# use public sets to support extending codes
OK_CODES = {Code.OK}
TIMEOUT_CODES = {Code.TIMEOUT}
CRASH_CODES = {Code.UNKNOWN, Code.INTERNAL, Code.UNIMPLEMENTED}
ERROR_CODES = set(Code) - CRASH_CODES - {Code.OK} - {Code.TIMEOUT}
_all_codes = OK_CODES | TIMEOUT_CODES | CRASH_CODES | ERROR_CODES
_missing_category = set(Code) - _all_codes
assert _missing_category == set(), f"missing category for codes: {_missing_category}"


@singledispatch
def as_error_code(error: BaseException) -> Code:
    """Use register on this method if having a code attribute is not enough."""
    return getattr(error, "code", Code.UNKNOWN)


@as_error_code.register(Code)
def _identity(error: Code):
    return error


@as_error_code.register(TimeoutError)
@as_error_code.register(ConcTimeoutError)
@as_error_code.register(AsyncTimeoutError)
def _timeout(error: TimeoutError) -> Code:
    return Code.TIMEOUT


def is_crash(code_or_error: str | BaseException):
    code = as_error_code(code_or_error)
    return code in CRASH_CODES


def is_ok(code_or_error: str | BaseException):
    code = as_error_code(code_or_error)
    return code in OK_CODES


def is_timeout(code_or_error: str | BaseException):
    code = as_error_code(code_or_error)
    return code in TIMEOUT_CODES


def is_error(code_or_error: str | BaseException):
    code = as_error_code(code_or_error)
    return code in ERROR_CODES


class BaseError(Exception):
    """Used when you want to define an init method for the error, e.g., for
    accessing fields."""

    code = Code.UNKNOWN
    msg_template = ""

    def __str__(self):
        if self.msg_template:
            return self.msg_template.format(**self.__dict__)
        args = ", ".join(
            f"{key}={value!r}"
            for key, value in self.__dict__.items()
            if not key.startswith("_")
        )
        return f"{type(self).__name__}({args})"

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        return str(self) == str(other)


def log_error(logger, error, level=logging.ERROR, *, prefix="") -> None:
    error_msg = repr(error)
    if prefix:
        error_msg = f"{prefix}:{error_msg}"
    logger.log(level, error_msg)
    if traceback__ := get_tb(error):
        logger.log(level, "".join(traceback.format_tb(traceback__)))


def get_tb(error: BaseException) -> TracebackType | None:
    """empty string if no traceback."""
    return getattr(error, "__traceback__", None)


def as_str_traceback_from_error(error: Exception) -> str:
    return as_str_traceback(getattr(error, "__traceback__", ""))


def as_str_traceback(tb: TracebackType | str | None) -> str:
    if tb:
        return "".join(traceback.format_tb(tb))
    return ""


def error_and_traceback(error: BaseException) -> str:
    lines = [repr(error)]
    if tb_str := as_str_traceback(get_tb(error)):
        lines.append(tb_str)
    return "\n".join(lines)


def log_error_callable(logger, prefix=""):
    return partial(log_error, logger, prefix=prefix)
