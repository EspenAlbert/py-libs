from model_lib.constants import (
    METADATA_DUMP_KEY,
    METADATA_MODEL_NAME_BACKUP_FIELD,
    METADATA_MODEL_NAME_FIELD,
    MODEL_DUMP_KEY,
    FileFormat,
)
from model_lib.serialize.dump import dump, dump_with_metadata
from model_lib.serialize.parse import parse_model_metadata

from model_lib import Event


class _MyModelWithAge(Event):
    name: str
    age: int
    city: str = "unknown"


def test_parse_with_extra_kwargs():
    model = _MyModelWithAge(name="test", age=22)
    raw = dump_with_metadata(model=model)
    model_back, metadata = parse_model_metadata(raw, extra_kwargs=dict(city="known"))
    assert model != model_back
    assert model_back.city == "known"


def test_parse_no_extra_kwargs():
    model = _MyModelWithAge(name="test", age=22)
    raw = dump_with_metadata(model=model)
    model_back, metadata = parse_model_metadata(raw)
    assert model_back == model


def test_dump_and_parse_a_str():
    raw_string = "raw string as a model"
    metadata = dict(a=1, b="ok", model_name="str")
    dumped = dump_with_metadata(raw_string, metadata)
    model, metadat_back = parse_model_metadata(dumped)
    assert model == raw_string
    assert metadat_back == metadata


def test_parse_with_model_name_backup():
    model = _MyModelWithAge(name="backup", age=11)
    model_dict = model.dict()
    metadata = {
        METADATA_MODEL_NAME_FIELD: "_UNKNOWN",
        METADATA_MODEL_NAME_BACKUP_FIELD: _MyModelWithAge.__name__,
    }
    dumped = dump(
        {MODEL_DUMP_KEY: model_dict, METADATA_DUMP_KEY: metadata}, FileFormat.json
    )
    model_back, metadata_back = parse_model_metadata(dumped)
    assert model_back == model
    assert metadata_back == metadata


def test_parse_directly():
    model = _MyModelWithAge(name="no_metadata", age=12)
    model_payload = model.dict()
    model_back, _ = parse_model_metadata(model_payload, t=_MyModelWithAge)
    assert model == model_back
