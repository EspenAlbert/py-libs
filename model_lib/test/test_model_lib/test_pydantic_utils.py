from datetime import timedelta

from model_lib.constants import FileFormat
from model_lib.pydantic_utils import timedelta_dumpable
from model_lib.serialize import dump, parse_model

from model_lib import Event


def test_timedelta_dumpable():
    class _MyModelTimedelta(Event):
        td: timedelta_dumpable

    model = _MyModelTimedelta(td=timedelta(hours=1, weeks=1))
    dumped = dump(model, FileFormat.yaml)
    model2 = parse_model(dumped, format=FileFormat.yaml, t=_MyModelTimedelta)
    assert model == model2
