from functools import cached_property

import pytest
from model_lib.errors import UnknownModelError
from model_lib.model_base import Entity, Event, SeqModel, model_name_to_t
from model_lib.model_dump import dump
from model_lib.pydantic_utils import IS_PYDANTIC_V2


class _MyEventModelBase(Event):
    pass


class _MyEntityModelBase(Entity):
    pass


def test_getting_model_classes():
    assert model_name_to_t(_MyEventModelBase.__name__) is _MyEventModelBase
    assert model_name_to_t(_MyEntityModelBase.__name__) is _MyEntityModelBase


class _MyModelXX:
    pass


def test_unknown_model_error():
    with pytest.raises(UnknownModelError):
        model_name_to_t(_MyModelXX.__name__)


class _MyModelWithCachedProperty(Entity):
    first: str = "one"
    second: str = "two"

    @cached_property
    def full(self) -> str:
        return f"{self.first}-{self.second}"


def test_comparing_two_instances_with_cached_property():
    i1 = _MyModelWithCachedProperty()
    i2 = _MyModelWithCachedProperty()
    assert i1 == i2
    assert i1.full == "one-two"
    assert i1 == i2
    assert i2.full == "one-two"
    assert i1 == i2


class _Person(Entity):
    name: str


if IS_PYDANTIC_V2:

    class _People(SeqModel[_Person]):
        pass

else:

    class _People(SeqModel[_Person]):
        __root__: list[_Person]


def test_iterating_over_people():
    p1 = _Person(name="p1")
    p2 = _Person(name="p2")
    people_list = [p1, p2]
    if IS_PYDANTIC_V2:
        people = _People(people_list)
    else:
        people = _People(__root__=people_list)
    assert len(people) == 2
    assert list(people) == people_list
    for i, person in enumerate(people):
        assert person == people_list[i]
    assert people[1] == p2
    assert dump(people) == people_list
