from datetime import datetime
from typing import Union

from freezegun import freeze_time
from pydantic import Field

from model_lib import (
    Entity,
    Event,
    FileFormat,
    dump,
    dump_with_metadata,
    parse_model,
    register_dumper,
)
from model_lib.serialize.parse import parse_payload, register_parser

dump_formats = list(FileFormat)
expected_dump_formats: list[str] = [
    "json",
    "pretty_json",
    "json_pretty",
    "yaml",
    "yml",
    "json_pydantic",
    "pydantic_json",
    "toml",
    "toml_compact",
]
missing_dump_formats: set[str] = set(FileFormat) - set(expected_dump_formats)  # type: ignore
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
    person = Person(age=99, name="espen")
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


def custom_dump(custom: CustomDumping):
    return dict(full_name=f"{custom.first_name} {custom.last_name}")


register_dumper(CustomDumping, custom_dump)


class CustomKafkaPayload:
    def __init__(self, body: str, topic: str):
        self.topic = topic
        self.body = body


def custom_parse_kafka(payload: CustomKafkaPayload, format: str) -> Union[dict, list]:
    return parse_payload(payload.body, format)


register_parser(CustomKafkaPayload, custom_parse_kafka)


def test_custom_dump():
    instance = CustomDumping("Espen", "Python")
    assert dump(instance, "json") == '{"full_name":"Espen Python"}'
    payload = CustomKafkaPayload(
        body='{"first_name": "Espen", "last_name": "Python"}', topic="some-topic"
    )
    assert parse_model(payload, t=CustomDumping) == instance
