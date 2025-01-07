from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, TypeVar

from zero_3rdparty.error import BaseError
from zero_3rdparty.id_creator import simple_id

logger = logging.getLogger(__name__)


def update_no_overwrite(source: dict[str, object], updates: dict[str, object]) -> None:
    """
    Warning:
        Will modify both source and updates

    >>> start = {"a": 1}
    >>> update_no_overwrite(start, {"a": 2})
    >>> start
    {'a': 1, 'a_1': 2}
    >>> update_no_overwrite(start, {"a": 3})
    >>> start
    {'a': 1, 'a_1': 2, 'a_2': 3}
    >>> update_no_overwrite(start, {"b": 4})
    >>> start
    {'a': 1, 'a_1': 2, 'a_2': 3, 'b': 4}
    >>> [update_no_overwrite(start, {"c": i}) for i in range(20)]
    [None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None]
    >>> "c_9" in start
    True
    >>> "c_10" in start
    False

    """
    existing = source.keys() & updates.keys()
    for key in existing:
        value = updates.pop(key)
        if value == source[key]:
            continue
        for i in range(1, 10):
            new_key = f"{key}_{i}"
            if new_key not in source:
                break
        else:
            logger.warning(f"many of the same key: {key}")
            random_suffix = simple_id(length=5)
            new_key = f"{key}_{random_suffix}"
        updates[new_key] = value
    source.update(updates)


KT = TypeVar("KT")
VT = TypeVar("VT")


def rename_keys(source: dict[str, VT], renames: dict[str, str]) -> dict[str, VT]:
    """
    >>> rename_keys({"a.2": 1, "b": 2}, {"a.2": "a"})
    {'a': 1, 'b': 2}
    """
    new_dict = {}
    for key, value in source.items():
        new_key = renames.get(key, key)
        new_dict[new_key] = value
    return new_dict


def pop_latest(d: dict[KT, VT]) -> VT:
    """
    >>> pop_latest({"a": 1, "b": 2})
    2
    >>> d = {"a": 1, "b": 2}
    >>> d["ok"] = "yes"
    >>> pop_latest(d)
    'yes'
    """
    _, value = d.popitem()
    return value


class MergeDictError(BaseError):
    def __init__(self, path: str):
        self.path: str = path


def merge(
    a: dict,
    b: dict,
    path: list[str] | None = None,
    allow_overwrite: bool = False,
    allow_new: bool = True,
) -> None:
    """merges b into a https://stackoverflow.com/questions/7204805/how-to-
    merge-dictionaries-of-dictionaries/7205107#7205107.

    >>> a = {1:{"a":"A"},2:{"b":"B"}}
    >>> merge(a, {2:{"c":"C"},3:{"d":"D"}})
    >>> a
    {1: {'a': 'A'}, 2: {'b': 'B', 'c': 'C'}, 3: {'d': 'D'}}
    >>> merge(a, {1: "OVERWRITE"}, allow_overwrite=False)
    Traceback (most recent call last):
    ...
    zero_3rdparty.dict_utils.MergeDictError: MergeDictError(path='1')
    >>> merge(a, {1: "OVERWRITE"}, allow_overwrite=True)
    >>> a
    {1: 'OVERWRITE', 2: {'b': 'B', 'c': 'C'}, 3: {'d': 'D'}}
    >>> before_no_new = dict(a="old")
    >>> merge(before_no_new, dict(a="new", b="ignored"), allow_overwrite=True, allow_new=False)
    >>> before_no_new
    {'a': 'new'}
    """
    if path is None:
        path = []
    for key, value in b.items():
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge(
                    a[key],
                    b[key],
                    path + [str(key)],
                    allow_overwrite=allow_overwrite,
                    allow_new=allow_new,
                )
            elif a[key] != value:
                if allow_overwrite:
                    a[key] = value
                else:
                    raise MergeDictError(path=".".join(path + [str(key)]))
        elif allow_new:
            a[key] = b[key]


def select_existing(existing_vars: dict, new_vars: dict) -> dict:
    """
    >>> select_existing(dict(a=1), dict(a=2, b=2))
    {'a': 2}
    >>> select_existing(dict(a=1, b=dict(c=1)), dict(a=2, b=2))
    {'a': 2, 'b': 2}
    >>> select_existing(dict(a=1, b=dict(c=1)), dict(a=2, b=dict(c=2)))
    {'a': 2, 'b': {'c': 2}}
    """
    new_d = {}
    for key, value in new_vars.items():
        old = existing_vars.get(key)
        if not old:
            continue
        if isinstance(old, dict) and isinstance(value, dict):
            new_value = select_existing(old, value)
            new_d[key] = new_value
            continue
        new_d[key] = value
    return new_d


def sort_keys(some_dict: dict[KT, VT]) -> dict[KT, VT]:
    """
    >>> sort_keys(dict(b=2, a=1, c=3))
    {'a': 1, 'b': 2, 'c': 3}
    >>> sort_keys(dict(b=2, a=1, c=dict(d=4, a=2)))
    {'a': 1, 'b': 2, 'c': {'a': 2, 'd': 4}}
    """

    def add_sorted_value(value: VT):
        return sort_keys(value) if isinstance(value, dict) else value

    return {key: add_sorted_value(some_dict[key]) for key in sorted(some_dict.keys())}  # type: ignore


def select_values(some_container: dict | list, allowed_values: tuple[type, ...]):
    def ok_value(value: Any):
        if isinstance(value, (dict, list)):
            return bool(value)
        return isinstance(value, allowed_values)

    def unpack(value: Any):
        return unpack_list_or_dict(value) if isinstance(value, (dict, list)) else value

    def unpack_list_or_dict(some_dict_or_list: dict | list):
        if isinstance(some_dict_or_list, dict):
            return {
                key: unpack(value)
                for key, value in some_dict_or_list.items()
                if ok_value(value)
            }
        else:
            return [unpack(value) for value in some_dict_or_list if ok_value(value)]

    return unpack_list_or_dict(some_container)


def as_case_insensitive(d: Mapping[str, VT]) -> dict[str, VT]:
    """
    >>> as_case_insensitive(dict(a=1, B=2, cD=3))
    {'a': 1, 'A': 1, 'B': 2, 'b': 2, 'cD': 3, 'cd': 3, 'CD': 3}
    """
    new: dict[str, VT] = {}

    def add_env(key: str, value: VT) -> None:
        new[key] = value
        new[key.lower()] = value
        new[key.upper()] = value

    for key, value in d.items():
        add_env(key, value)
    return new
