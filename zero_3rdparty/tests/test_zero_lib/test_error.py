import logging

from zero_3rdparty.error import (
    BaseError,
    Code,
    KwargsError,
    is_crash,
    is_error,
    is_ok,
    is_timeout,
)

logger = logging.getLogger(__name__)


class MyError(KwargsError):
    pass


def test_kwargs_exception_str():
    error = MyError(dummy=True, error="test_error", number=3)
    assert str(error) == "MyError(dummy=True,error='test_error',number=3)"
    assert error.dummy
    assert error.error == "test_error"
    assert error.number == 3
    assert error.number == 3
    assert is_crash(error)
    assert not is_error(error)
    assert not is_ok(error)
    assert not is_timeout(error)


class MyBaseError(BaseError):
    def __init__(self, name: str):
        self.name = name


def test_base_error():
    error = MyBaseError("ok")
    error.code = Code.OK
    assert is_ok(error)
    assert is_ok(Code.OK)
    error.code = Code.TIMEOUT
    assert is_timeout(error)
    assert is_timeout(Code.TIMEOUT)
    error.code = Code.INVALID_ARGUMENT
    assert is_error(error)
    assert is_error(Code.INVALID_ARGUMENT)
