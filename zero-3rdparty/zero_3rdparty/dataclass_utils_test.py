from dataclasses import dataclass

from zero_3rdparty.dataclass_utils import copy, field_names, key_values, values


@dataclass
class MyTestClass:
    name: str
    age: int
    fictive: bool = True


def test_field_names():
    instance = MyTestClass(name="Espen", age=99)
    assert field_names(instance) == ["name", "age", "fictive"]
    assert field_names(MyTestClass) == ["name", "age", "fictive"]


def test_values():
    instance = MyTestClass(name="espen", age=99)
    assert values(instance) == ["espen", 99, True]


def test_copy(subtests):
    instance = MyTestClass(name="name1", age=1, fictive=False)
    with subtests.test("copy no update"):
        instance2 = copy(instance)
        assert instance == instance2
    with subtests.test("copy with update"):
        instance3 = copy(instance, update={"fictive": True})
        assert instance3.fictive
    with subtests.test("copy with exclude"):
        instance4 = copy(instance, exclude={"fictive"})
        assert instance4.fictive
    with subtests.test("copy with update and exclude"):
        instance5 = copy(instance, update={"age": 2}, exclude=["fictive"])
        assert instance5 == MyTestClass(name="name1", age=2)


def test_key_values(subtests):
    instance = MyTestClass("name2", 22)
    with subtests.test("no filter"):
        assert key_values(instance) == {"name": "name2", "age": 22, "fictive": True}
    with subtests.test("with filter"):

        def skip_age(field_name: str) -> bool:
            return field_name != "age"

        assert key_values(instance, filter=skip_age) == {
            "fictive": True,
            "name": "name2",
        }
