from dataclasses import dataclass

from zero_3rdparty.dict_utils import select_values


@dataclass
class MyClass:
    name: str


def test_select_values():
    some_nested_object = {
        "strings": "ignored",
        "object": MyClass("not_ignored"),
        "nested": [MyClass("kept"), 22],
    }
    assert select_values(some_nested_object, (MyClass,)) == {
        "nested": [MyClass(name="kept")],
        "object": MyClass(name="not_ignored"),
    }
