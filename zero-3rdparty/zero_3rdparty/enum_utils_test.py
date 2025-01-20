from zero_3rdparty.enum_utils import StrEnum


class _Status(StrEnum):
    CREATED = "CREATED"
    STARTED = "STARTED"
    FINISHED = "FINISHED"


def test_comparison():
    assert _Status.CREATED == "CREATED"


def test_repr():
    assert repr(_Status.STARTED) == repr("STARTED")


def test_str():
    assert f"{_Status.STARTED}" == "STARTED"


def test_is_str():
    assert isinstance(_Status.CREATED, str)
