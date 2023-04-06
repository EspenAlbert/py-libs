from inspect import isclass
from typing import Dict, Iterable, Optional, Type, TypeVar

from zero_lib.iter_utils import first_or_none

V = TypeVar("V")


class TypeDict(Dict[Type, Iterable[V]]):
    """Stores a list of Iterable[Tuple[V, bool]] But when the value is get, the
    iterator of the __getitem__ is returned."""

    def __missing__(self, key):
        return []

    def add(self, key: Type, value: V, strict=False):
        assert isclass(key), f"not a class: {key}, value={value}"
        values = super().__getitem__(key)
        if not values:
            super().__setitem__(key, values)
        assert isinstance(values, list)
        values.append((value, strict))

    def get_by_key_and_strict(self, key: Type, strict=False) -> Optional[V]:
        assert isclass(key), f"not a class: {key}"
        values = super().__getitem__(key)
        return first_or_none(
            value for value, each_strict in values if strict == each_strict
        )

    def filter(self, key: Type, strict: bool, base_t: Type):
        return strict is False or key is base_t

    def __getitem__(self, item: Type) -> Iterable[V]:
        for base_t in item.__mro__[:-1]:  # skip object
            for value, strict in super().get(base_t, []):
                if self.filter(item, strict, base_t):
                    yield value

    def pop_specific(self, key: Type, value: V, strict=False):
        values: list = super().__getitem__(key)
        try:
            values.remove((value, strict))
        except ValueError:
            raise KeyError(str((key.__name__, value, strict)))
        return value

    def __len__(self):
        return sum(len(values) for values in self.values())
