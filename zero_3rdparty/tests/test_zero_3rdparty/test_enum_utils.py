from datetime import datetime
from typing import Dict

import pytest
from model_lib.constants import FileFormat
from zero_3rdparty.datetime_utils import utc_now
from zero_3rdparty.enum_utils import StrEnum

from model_lib import Event, dump


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


class _MyModel(Event):
    status: _Status = _Status.STARTED
    name: str


def test_dumping_value():
    model = _MyModel(name="ok")
    dumped = dump(model, FileFormat.json)
    assert dumped == '{"status":"STARTED","name":"ok"}'


class _MyModelStatusKeys(Event):
    status_ts: Dict[_Status, datetime]


@pytest.mark.freeze_time("2020-01-01")
def test_dumping_key():
    model = _MyModelStatusKeys(status_ts={_Status.CREATED: utc_now()})
    dumped = dump(model, FileFormat.json)
    assert dumped == '{"status_ts":{"CREATED":"2020-01-01T00:00:00+00:00"}}'


def test_is_str():
    assert isinstance(_Status.CREATED, str)
