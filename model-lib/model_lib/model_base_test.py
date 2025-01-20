from functools import cached_property

import pytest

from model_lib.errors import UnknownModelError
from model_lib.model_base import Entity, Event, SeqModel, model_name_to_t
from model_lib.model_dump import dump


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


class _People(SeqModel[_Person]):
    pass


def test_iterating_over_people():
    p1 = _Person(name="p1")
    p2 = _Person(name="p2")
    people_list = [p1, p2]
    people = _People(people_list)
    assert len(people) == 2
    assert list(people) == people_list  # type: ignore
    # sourcery skip: no-loop-in-tests
    for i, person in enumerate(people):  # type: ignore
        assert person == people_list[i]
    assert people[1] == p2
    assert dump(people) == people_list
