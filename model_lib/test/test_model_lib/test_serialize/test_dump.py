from model_lib import Event
from model_lib.constants import FileFormat
from model_lib.metadata import EventMetadata, iter_tags
from model_lib.serialize import parse_model_metadata
from model_lib.serialize.dump import dump_with_metadata


class _MyModel(Event):
    name: str


class _MyMetadataModel(Event):
    other_name: str


def test_dumping_metadata_with_tags(file_regression, subtests):
    tags = [
        ("other_key", _MyMetadataModel(other_name="metadata")),
        ("normal_key", "normal_value"),
    ]
    model = _MyModel(name="model")
    dumped = dump_with_metadata(
        model,
        metadata={EventMetadata.tags: tags},
        format=FileFormat.yaml,
    )
    file_regression.check(dumped, extension=".yaml")

    model_again, metadata = parse_model_metadata(dumped, FileFormat.yaml)
    with subtests.test("parsing metadata"):
        tags_parsed = []
        for i, (key, value) in enumerate(iter_tags(metadata), start=1):
            if i == 1:
                tags_parsed.append((key, _MyMetadataModel(**value)))
            else:
                tags_parsed.append((key, value))
        assert tags_parsed == tags
    with subtests.test("parse model"):
        assert model_again == model
