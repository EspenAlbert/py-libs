from dataclasses import dataclass
from typing import ClassVar

import pytest

from zero_3rdparty.dependency import (
    DependencyNotSet,
    MissingDependencies,
    Provider,
    ReBindingError,
    as_dependency_cls,
    bind_instances,
    dependency,
    instance,
    instance_or_inferred,
    instance_or_none,
    validate_dependencies,
)


@dataclass
class _MyClass:
    name: str


@dataclass
class _MyClassUser:
    my_cls: ClassVar[_MyClass] = dependency(_MyClass)

    def get_name(self) -> str:
        return self.my_cls.name


@dataclass
class _MySubClass(_MyClass):
    pass


def test_dep(subtests):
    cls_user = _MyClassUser()
    with subtests.test("dependency descriptor raises AttributeError"):
        with pytest.raises(AttributeError):
            cls_user.my_cls
    with subtests.test("as_dependency_cls"):
        assert as_dependency_cls(_MyClassUser.my_cls) is _MyClass
    with subtests.test("MissingDependencies"):
        with pytest.raises(MissingDependencies) as exc:
            validate_dependencies([cls_user])
        assert set(exc.value.missing_dependencies.keys()) == {_MyClass}
    with subtests.test("DependencyNotSet"):
        with pytest.raises(DependencyNotSet) as exc:
            instance(_MyClass)
        assert exc.value.cls is _MyClass
    with subtests.test("instance_or_none"):
        assert instance_or_none(_MyClass) is None
    with subtests.test("bind_instances"):
        bind_instances({_MyClass: _MyClass(name="n1")}, clear_first=True)
        assert instance(_MyClass) == _MyClass(name="n1")
    with subtests.test("ReBindingError"):
        with pytest.raises(ReBindingError) as exc:
            bind_instances({_MyClass: _MyClass(name="n2")})
        assert exc.value.classes == [_MyClass]
    with subtests.test("ReBinding allowed"):
        bind_instances({_MyClass: _MyClass(name="n3")}, allow_re_binding=True)
        assert instance(_MyClass).name == "n3"
    with subtests.test("dependency descriptor"):
        assert cls_user.get_name() == "n3"
    with subtests.test("dependency descriptor updates"):
        bind_instances({_MyClass: _MyClass(name="n4")}, allow_re_binding=True)
        assert cls_user.get_name() == "n4"
    with subtests.test("MissingDependencies allow_binding"):
        bind_instances({}, clear_first=True)
        validate_dependencies([cls_user, _MyClass(name="n5")], allow_binding=True)
        assert instance(_MyClass).name == "n5"
    with subtests.test("Provider"):
        counter = 0

        def my_provider():
            nonlocal counter
            counter += 1
            return _MyClass(name=f"n-{counter}")

        bind_instances({_MyClass: Provider(my_provider)}, allow_re_binding=True)

        instances = [instance(_MyClass) for _ in range(10)]
        assert instances[-1] == _MyClass(name="n-10")
    with subtests.test("instance_or_inferred"):
        bind_instances({_MyClass: _MySubClass(name="inferred")}, clear_first=True)
        with pytest.raises(DependencyNotSet):
            instance(_MySubClass)
        assert instance_or_inferred(_MySubClass).name == "inferred"
        assert instance(_MySubClass).name == "inferred"
