from contextlib import suppress
from functools import singledispatch
from typing import (
    Any,
    Dict,
    Iterable,
    MutableMapping,
    Optional,
    Type,
    TypeVar,
    Union,
    overload,
)

DictList = Union[list, Dict[str, object]]


def read_nested_or_none(container: DictList, simple_path: str) -> Optional[object]:
    """
    >>> read_nested_or_none({"a": [{"b": 2}]}, "a.[0].b")
    2
    >>> read_nested_or_none({"a": [{"b": 2}]}, "a[0].b")
    """
    with suppress(Exception):
        return read_nested(container, simple_path)


def read_nested(container: DictList, simple_path: str) -> Any:
    last_container, final_accessor = _follow_path(container, simple_path)
    return last_container[final_accessor]


def iter_nested_keys(container: MutableMapping, root_path: str = "") -> Iterable[str]:
    """
    >>> list(iter_nested_keys(dict(a=dict(b="c"))))
    ['a', 'a.b']
    >>> list(iter_nested_keys(dict(a=dict(b="c", c=["1", "2"]))))
    ['a', 'a.b', 'a.c']
    >>> list(iter_nested_keys(dict(a=dict(b="c", c=["1", "2"]), d="2")))
    ['a', 'a.b', 'a.c', 'd']
    """
    for key, child in container.items():
        child_root_path = f"{root_path}.{key}" if root_path else key
        if isinstance(key, str):
            yield child_root_path
        if isinstance(child, dict):
            yield from iter_nested_keys(child, child_root_path)


T = TypeVar("T")
_missing = object()


def iter_nested_key_values(
    container: MutableMapping, type_filter: Type[T] = _missing
) -> Iterable[tuple[str, T]]:
    """
    >>> container_example = dict(a="ok", b=dict(c="nested"))
    >>> list(iter_nested_key_values(container_example, str))
    [('a', 'ok'), ('b.c', 'nested')]
    """
    for key in iter_nested_keys(container):
        value = read_nested(container, key)
        if type_filter is _missing or isinstance(value, type_filter):
            yield key, value


@overload
def update(
    container: Dict[str, object],
    simple_path: str,
    new_value: object,
    ensure_parents: bool = True,
) -> Dict[str, object]:
    ...


@overload
def update(
    container: list, simple_path: str, new_value: object, ensure_parents: bool = True
) -> list:
    ...


def update(
    container: DictList,
    simple_path: str,
    new_value: object,
    ensure_parents: bool = True,
) -> DictList:
    """Sets the new_value on container[simple_path.

    >>> update({}, "valueFrom.fieldRef.fieldPath", "metadata.namespace")
    {'valueFrom': {'fieldRef': {'fieldPath': 'metadata.namespace'}}}
    >>> update({'metadata': {'name': 'kibana'}}, 'metadata.namespace', "kibana")
    {'metadata': {'name': 'kibana', 'namespace': 'kibana'}}
    >>> update({}, 'metadata.namespace', "kibana", ensure_parents=False)
    Traceback (most recent call last):
    ...
    KeyError: 'metadata'
    >>> update({}, 'metadata.namespace', "kibana", ensure_parents=True)
    {'metadata': {'namespace': 'kibana'}}
    >>> update({}, 'spec.ports.[0]', {'name': "kibana", 'port': 5601}, ensure_parents=True)
    {'spec': {'ports': [{'name': 'kibana', 'port': 5601}]}}
    >>> update({'spec': {'ports': [{'name': 'kibana', 'port': 5601}]}}, 'spec.ports.[0].port', 3333, ensure_parents=True)
    {'spec': {'ports': [{'name': 'kibana', 'port': 3333}]}}
    >>> update({'containers': [{}, {}]}, 'containers.[99]', {'new': True}, ensure_parents=True)
    {'containers': [{}, {}, {'new': True}]}

    Args:
        container: To update can be any subclass of dict or list
        simple_path: wrapped digits interpreted as indexes in a list
            e.g. 'metadata.namespace', 'ports.[0]'
        new_value: what the new_value is
        ensure_parents: Will not fail if both metadata and namespace does not exist
    Returns:
        container passed in
    """
    follower = _safe_follow_path if ensure_parents else _follow_path
    last_container, final_accessor = follower(container, simple_path)
    _insert_or_update(last_container, final_accessor, new_value)
    return container


def _as_accessor(
    accessor: str, start_symbols: str = "([{", end_symbols: str = ")]}"
) -> Union[str, int]:
    """
    >>> _as_accessor("a")
    'a'
    >>> _as_accessor("(0)")
    0
    >>> _as_accessor("[0]")
    0
    >>> _as_accessor("[5555]")
    5555
    >>> _as_accessor("[000")
    '[000'
    >>> _as_accessor("{55}")
    55
    >>> _as_accessor("{}")
    '{}'
    """
    assert accessor
    if (
        accessor[0] in start_symbols
        and accessor[-1] in end_symbols
        and (without_brackets := accessor[1:-1])
        and without_brackets.isdigit()
    ):
        return int(without_brackets)
    return accessor


def _safe_follow_path(container: DictList, simple_path: str):
    current = container
    accessors = simple_path.split(".")
    *must_exist, final = accessors
    final_accessor = _as_accessor(final)
    for i, accessor in enumerate(must_exist):
        accessor = _as_accessor(accessor)
        try:
            current = current[accessor]
        except LookupError:
            last_container = [] if isinstance(final_accessor, int) else {}
            child_container = _create_nested_container(
                last_container, must_exist[i + 1 :]
            )
            if isinstance(accessor, int):
                current.append(child_container)
            else:
                current[accessor] = child_container
            return last_container, final_accessor
    return current, final_accessor


def _create_nested_container(
    last_container: DictList, accessors: Iterable[str]
) -> DictList:
    """
    >>> _create_nested_container([], ["a", "b", "c"])
    {'a': {'b': {'c': []}}}
    >>> _create_nested_container([], ["ports", "[0]"])
    {'ports': [[]]}
    >>> _create_nested_container({}, ["ports", "[0]", "name"])
    {'ports': [{'name': {}}]}
    >>> _create_nested_container({}, ["ports", "[1]", "name"])
    Traceback (most recent call last):
    ...
    AssertionError: no list existed at path ports.[1].name
    """
    for accessor in reversed(accessors):
        accessor = _as_accessor(accessor)
        if isinstance(accessor, int):
            assert accessor == 0, f"no list existed at path {'.'.join(accessors)}"
            last_container = [last_container]
        else:
            last_container = {accessor: last_container}
    return last_container


def _follow_path(container: DictList, simple_path: str):
    current = container
    accessors = simple_path.split(".")
    *must_exist, final = accessors
    for accessor in must_exist:
        accessor = _as_accessor(accessor)
        current = current[accessor]
    final_accessor = _as_accessor(final)
    return current, final_accessor


@singledispatch
def _insert_or_update(current: object, final_accessor: str, new_value: object):
    raise NotImplementedError()


@_insert_or_update.register(dict)
def _insert_or_update_dict(current: dict, final_accessor: str, new_value: object):
    current[final_accessor] = new_value


@_insert_or_update.register(list)
def _insert_or_update_list(current: list, final_accessor: int, new_value: object):
    if len(current) <= final_accessor:
        current.append(new_value)
    else:
        current[final_accessor] = new_value
