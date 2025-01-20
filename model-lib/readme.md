# Model-lib - pydantic base models with convenient dump methods

## Installation
`pip install 'model-lib[full]'`

## Model-lib tutorial: What classes to use as base classes, how to serialize them, and add metadata
- A library built on top of [pydantic](https://docs.pydantic.dev/latest/)
- Both pydantic v1 and v2 are supported
- The models: `Event` and `Entity` are subclassing [pydantic.BaseModel](https://pydantic-docs.helpmanual.io/usage/models/)
    - Event is immutable
    - Entity is mutable
    - The specific configuration are:
        - Automatic registering for dumping to the various formats
        - Support different serializers for yaml/json/pretty_json/toml
        - use_enum_values
        - see [model_base](model_lib/model_base.py) for details
- Use `dump(model|payload, format) -> str`
  - if using an `Event|Entity` it should "just-work"
  - Alternatively, support custom dumping with `register_dumper(instance_type: Type[T],dump_call: DumpCall)` (see example below)
- Use `parse_payload(payload, format)` to parse to a `dict` or `list`
  - bytes
  - str
  - pathlib.Path (format not necessary if file has extension: `.yaml|.yml|json|toml`)
  - dict|list will be returned directly
  - supports `register_parser` for adding e.g., a parser for KafkaMessage
- Use `parse_model(payload, t=Type, format)` to parse and create a model
  - `t` not necessary if class name stored in `metadata.model_name` (see example below)
  - format not necessary if parsing from a file with extension

```python
from datetime import datetime

from freezegun import freeze_time
from pydantic import Field

from model_lib import (
    Entity,
    Event,
    dump,
    dump_with_metadata,
    parse_model,
    FileFormat,
    register_dumper,
)
from model_lib.serialize.parse import register_parser, parse_payload

dump_formats = list(FileFormat)
expected_dump_formats: list[str] = [
    "json",
    "pretty_json",
    "yaml",
    "yml",
    "json_pydantic",
    "pydantic_json",
    "toml",
    "toml_compact",
]
missing_dump_formats = set(FileFormat) - set(expected_dump_formats)
assert not missing_dump_formats, f"found missing dump formats: {missing_dump_formats}"


class Birthday(Event):
    """
    >>> birthday = Birthday()
    """

    date: datetime = Field(default_factory=datetime.utcnow)


class Person(Entity):
    """
    >>> person = Person(name="espen", age=99)
    >>> person.age += 1 # mutable
    >>> person.age
    100
    """

    name: str
    age: int


_pretty_person = """\
{
  "age": 99,
  "name": "espen"
}"""


def test_show_dumping():
    with freeze_time("2020-01-01"):
        birthday = Birthday(date=datetime.utcnow())
        # can dump non-primitives e.g., datetime
        assert dump(birthday, "json") == '{"date":"2020-01-01T00:00:00"}'
    person = Person(name="espen", age=99)
    assert dump(person, "yaml") == "name: espen\nage: 99\n"
    assert dump(person, "pretty_json") == _pretty_person


_metadata_dump = """\
model:
  name: espen
  age: 99
metadata:
  model_name: Person
"""


def test_show_parsing(tmp_path):
    path_json = tmp_path / "example.json"
    path_json.write_text(_pretty_person)
    person = Person(name="espen", age=99)
    assert parse_model(path_json, t=Person) == person
    assert dump_with_metadata(person, format="yaml") == _metadata_dump
    path_yaml = tmp_path / "example.yaml"
    path_yaml.write_text(_metadata_dump)
    assert parse_model(path_yaml) == person  # metadata is used to find the class


class CustomDumping:
    def __init__(self, first_name: str, last_name: str):
        self.first_name = first_name
        self.last_name = last_name

    def __eq__(self, other):
        if isinstance(other, CustomDumping):
            return self.__dict__ == other.__dict__
        return super().__eq__(other)


def custom_dump(custom: CustomDumping) -> dict:
    return dict(full_name=f"{custom.first_name} {custom.last_name}")


register_dumper(CustomDumping, custom_dump)


class CustomKafkaPayload:
    def __init__(self, body: str, topic: str):
        self.topic = topic
        self.body = body


def custom_parse_kafka(payload: CustomKafkaPayload, format: str) -> dict | list: # use Union[dict, list] if py3.9
    return parse_payload(payload.body, format)


register_parser(CustomKafkaPayload, custom_parse_kafka)


def test_custom_dump():
    instance = CustomDumping("Espen", "Python")
    assert dump(instance, "json") == '{"full_name":"Espen Python"}'
    payload = CustomKafkaPayload(
        body='{"first_name": "Espen", "last_name": "Python"}', topic="some-topic"
    )
    assert parse_model(payload, t=CustomDumping) == instance
```
