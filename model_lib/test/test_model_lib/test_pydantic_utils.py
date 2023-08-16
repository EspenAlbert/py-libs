from datetime import timedelta

import pydantic
from model_lib.constants import FileFormat
from model_lib.pydantic_utils import IS_PYDANTIC_V2, parse_object_as, timedelta_dumpable
from model_lib.serialize import dump, parse_model
from pydantic import BaseModel, Field
from zero_3rdparty.iter_utils import ignore_falsy

from model_lib import Event


class _ExampleModel(BaseModel):
    name: str


def test_parse_object_as():
    found = parse_object_as(_ExampleModel, {"name": "test"})
    assert found == _ExampleModel(name="test")


def test_timedelta_dumpable():
    class _MyModelTimedelta(Event):
        td: timedelta_dumpable

    model = _MyModelTimedelta(td=timedelta(hours=1, weeks=1))
    dumped = dump(model, FileFormat.yaml)
    model2 = parse_model(dumped, format=FileFormat.yaml, t=_MyModelTimedelta)
    assert model == model2


if IS_PYDANTIC_V2:
    from pydantic import model_serializer

    class _ExampleDumpModel(BaseModel):
        name: str
        items: list[str] = Field(default_factory=list)

        @model_serializer(mode="wrap")
        def ignore_falsy(
            self,
            nxt: pydantic.SerializerFunctionWrapHandler,
            _: pydantic.FieldSerializationInfo,
        ):
            serialized = nxt(self)
            return ignore_falsy(**serialized)

    def test_model_serializer():
        model = _ExampleDumpModel(name="no_items")
        assert model.model_dump() == {"name": "no_items"}
