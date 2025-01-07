from dataclasses import dataclass
from typing import Type

import pytest

from zero_3rdparty.type_dict import TypeDict


class _Base:
    pass


class _SubBase(_Base):
    pass


class _SubSubBase(_SubBase):
    pass


class _NormalCls:
    pass


@dataclass
class _TypeDictParam:
    name: str
    add_cls: Type
    get_cls: Type
    strict: bool = False

    @property
    def expected_count(self):
        is_subclass_ = issubclass(self.get_cls, self.add_cls)
        same_cls = self.get_cls is self.add_cls
        return int(is_subclass_ and (self.strict is False or same_cls))


# fmt: off
_TYPE_TEST_PARAMS = [
    # Good cases
    _TypeDictParam(name="same cls", add_cls=_Base, get_cls=_Base, strict=False),
    _TypeDictParam(name="same cls & strict", add_cls=_Base, get_cls=_Base, strict=True),
    _TypeDictParam(name="sub cls", add_cls=_Base, get_cls=_SubBase, strict=False),
    _TypeDictParam(name="sub_sub cls", add_cls=_Base, get_cls=_SubSubBase, strict=False),
    # Bad cases
    _TypeDictParam(name="different cls", add_cls=_Base, get_cls=_NormalCls,
                   strict=False),
    _TypeDictParam(name="sub cls strict", add_cls=_Base, get_cls=_SubBase, strict=True),
    _TypeDictParam(name="sub_sub cls strict", add_cls=_Base, get_cls=_SubSubBase,
                   strict=True),
]
# fmt: on

GOOD_CASES = 4
assert all(p.expected_count == 1 for p in _TYPE_TEST_PARAMS[:GOOD_CASES])
assert all(p.expected_count == 0 for p in _TYPE_TEST_PARAMS[GOOD_CASES:])


@pytest.mark.parametrize("param", _TYPE_TEST_PARAMS, ids=lambda p: p.name)
def test_type_dict(param):
    d = TypeDict()
    d.add(param.add_cls, 1, strict=param.strict)
    get_cls = param.get_cls
    actual_count = len(list(d[get_cls]))
    assert actual_count == param.expected_count


def test_type_dict_add_many():
    d = TypeDict()
    COUNT = 100
    for i in range(COUNT):
        d.add(_Base, i)
    assert len(d) == COUNT


def test_deleting():
    d = TypeDict()
    d[_Base] = 2
    assert _Base in d
    del d[_Base]
    assert _Base not in d
    with pytest.raises(KeyError):
        del d[_Base]


def test_popping():
    d = TypeDict()
    d.add(_Base, 2)
    popped = d.pop(_Base)
    assert popped == [(2, False)]
    with pytest.raises(KeyError):
        d.pop((_Base, False))


@pytest.mark.parametrize("strict", [True, False])
def test_get_by_key_and_strict_ok(strict):
    d = TypeDict()
    d.add(_Base, 2, strict=strict)
    assert d.get_by_key_and_strict(_Base, strict) == 2


@pytest.mark.parametrize("strict", [True, False])
def test_get_by_key_and_strict_fail(strict):
    d = TypeDict()
    d.add(_Base, 2, strict=strict)
    assert not d.get_by_key_and_strict(_Base, not strict)


def test_pop_specific():
    d = TypeDict()
    d.add(_Base, 1, strict=True)
    d.add(_Base, 2, strict=False)
    assert len(d) == 2
    assert d.pop_specific(_Base, 1, strict=True) == 1
    assert len(d) == 1
    with pytest.raises(KeyError) as exc:
        assert d.pop_specific(_Base, 1, strict=True) == 1
    assert str(exc.value) == "\"('_Base', 1, True)\""
