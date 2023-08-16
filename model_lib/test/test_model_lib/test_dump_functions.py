from functools import cached_property

from model_lib.constants import FileFormat
from model_lib.model_dump import dump
from model_lib.pydantic_utils import IS_PYDANTIC_V2, model_json
from pydantic import Field

from model_lib import Entity
from model_lib import dump as dump_format
from model_lib import dump_ignore_falsy

if IS_PYDANTIC_V2:
    from pydantic import RootModel

    BaseAsList = RootModel[list[str]]
else:

    class BaseAsList(Entity):
        __root__: list[str]


class RootAsChild(Entity):
    pets: BaseAsList
    owner: str

    @cached_property
    def owner_prop(self):
        return f"{self.owner}-prop"


def test_compare_dump_behavior_with_pydantic():
    model = RootAsChild(pets=["p1", "p2"], owner="bob")
    pydantic_json = model_json(model)
    if IS_PYDANTIC_V2:
        assert pydantic_json == '{"pets":["p1","p2"],"owner":"bob"}'
    else:
        assert pydantic_json == '{"pets": ["p1", "p2"], "owner": "bob"}'
    assert dump_format(model, "json") == '{"pets":["p1","p2"],"owner":"bob"}'
    child = RootAsChild(pets=["p1", "p2"], owner="bob")
    assert child.owner_prop == "bob-prop"
    # example of property also dumped in default json for pydantic v1
    if IS_PYDANTIC_V2:
        assert model_json(child) == '{"pets":["p1","p2"],"owner":"bob"}'
    else:
        assert (
            child.json()
            == '{"pets": ["p1", "p2"], "owner": "bob", "owner_prop": "bob-prop"}'
        )


@dump_ignore_falsy
class _MyModel(Entity):
    name: str
    my_list: list[str] = Field(default_factory=list)


class _MyParentModel(Entity):
    instances: list[_MyModel]


def test_dump_ignore_falsy(file_regression):
    from model_lib.serialize import dump as dump_to_json

    child1 = _MyModel(name="c1", my_list=["a"])
    child2 = _MyModel(name="c2")
    parent = _MyParentModel(instances=[child1, child2])
    file_regression.check(dump_to_json(parent, FileFormat.json), extension=".json")


class _MyCachedPropModel(Entity):
    name: str
    last_name: str

    @cached_property
    def full_name(self):
        return f"{self.name} {self.last_name}"


class _ParentWithCached(Entity):
    child: _MyCachedPropModel


def test_dumping_should_not_include_cached_property():
    instance = _MyCachedPropModel(name="n", last_name="ln")
    assert dump(instance) == dict(name="n", last_name="ln")
    assert instance.full_name == "n ln"
    assert dump(instance) == dict(name="n", last_name="ln")
    parent = _ParentWithCached(child=instance)
    assert dump(parent) == {"child": _MyCachedPropModel(last_name="ln", name="n")}
    assert dump_format(parent, "json") == '{"child":{"name":"n","last_name":"ln"}}'
