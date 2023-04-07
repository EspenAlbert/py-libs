from datetime import datetime

from freezegun import freeze_time
from pydantic import Field

from model_lib import Entity, Event, dump, dump_with_metadata, parse_model


class Birthday(Event):
    """
    >>> birthday = Birthday()
    >>> birthday.date = datetime.utcnow()
    Traceback (most recent call last):
    ...
    TypeError: "Birthday" is immutable and does not support item assignment
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
