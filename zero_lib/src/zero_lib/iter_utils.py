import inspect
from collections import ChainMap, defaultdict
from collections.abc import Generator
from functools import singledispatch
from itertools import chain, tee
from types import ModuleType
from typing import (
    Any,
    AsyncIterable,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

T = TypeVar("T")


async def first_async(async_iter: AsyncIterable[T], default=None) -> Optional[T]:
    async for t in async_iter:
        return t
    return default


def want_set(maybe_set: object) -> set:
    return maybe_set if isinstance(maybe_set, set) else set(want_list(maybe_set))


@singledispatch
def want_list(maybe_list: object) -> list:
    """
    >>> want_list((1, 2, 3))
    [1, 2, 3]
    """
    return [maybe_list]


@want_list.register
def _already_list(maybe_list: list) -> list:
    return maybe_list


@want_list.register
def _empty_list_on_none(maybe_list: None) -> list:
    return []


@want_list.register
def _exhaust_generator(maybe_list: Generator):
    return list(maybe_list)


@want_list.register
def _convert_tuple(maybe_list: tuple) -> list:
    return list(maybe_list)


def unique_instance_iter(iterable: Iterable[T]) -> Iterable[T]:
    seen_ids = set()
    for instance in iterable:
        instance_id = id(instance)
        if instance_id in seen_ids:
            continue
        yield instance
        seen_ids.add(instance_id)


def flat_map(iterable: Iterable[Iterable[T]]) -> Iterable[T]:
    """
    >>> list(flat_map([[1, 2, 3], [4,5,6]]))
    [1, 2, 3, 4, 5, 6]
    >>> list(flat_map([{1: 2, 3:4}.values(), {5:6, 7:8}.values()]))
    [2, 4, 6, 8]
    >>> dict(flat_map([{1: 2, 3:4}.items(), {5:6, 7:8}.items()]))
    {1: 2, 3: 4, 5: 6, 7: 8}
    """
    return chain.from_iterable(iterable)


def first(iterable: Iterable[Any], first_type: Type[T] = object) -> T:
    """
    >>> first(['a', 'b', 2], int)
    2
    >>> first(['a', 'b', 2], float)
    Traceback (most recent call last):
    ...
    StopIteration
    >>> first(['a', 'b', 2])
    'a'
    """
    return next(filter_on_type(iterable, first_type))


def first_or_none(
    iterable: Iterable[Any],
    first_type: Type[T] = object,
    *,
    condition: Callable[[T], bool] = None,
    default: Optional[T] = None,
) -> Optional[T]:
    """
    >>> first_or_none(['a', 'b', 2], float)

    >>> first_or_none(['a', 'b', 2], int)
    2
    >>> first_or_none([1,2,3], condition=lambda a: a < 0)

    >>> first_or_none([1,2,3], condition=lambda a: a > 2)
    3
    """
    if condition:
        return next((instance for instance in iterable if condition(instance)), default)
    return next(filter_on_type(iterable, first_type), default)


def filter_on_type(iterable: Iterable[Any], t: Type[T]) -> Iterable[T]:
    """
    >>> list(filter_on_type(['a', 'b', 2, 3.0, 4], str))
    ['a', 'b']
    >>> list(filter_on_type(['a', 'b', 2, 3.0, 4], float))
    [3.0]
    >>> list(filter_on_type(['a', 'b', 2, 3.0, 4], int))
    [2, 4]
    >>> list(filter_on_type(['a', 'b', 2, 3.0, 4], bool))
    []
    """
    for i in iterable:
        if isinstance(i, t):
            yield i


def public_dict(
    cls: Union[Type, ModuleType], recursive: bool = False
) -> Dict[str, Any]:
    """
    Args:
        recursive: go up the chain of base classes
    """
    if not inspect.isclass(cls) and not inspect.ismodule(cls):
        cls = type(cls)
    if recursive and cls is not object:
        maps = [public_dict(parent) for parent in cls.__mro__]
        return dict(ChainMap(*maps))
    return {
        name: value for name, value in vars(cls).items() if not name.startswith("_")
    }


def public_values(cls: Union[Type, ModuleType], sorted_=True) -> List[Any]:
    public_vars = public_dict(cls)
    if sorted_:
        sorted_kv = sorted(public_vars.items(), key=lambda kv: kv[0])
        return [kv[1] for kv in sorted_kv]
    return list(public_vars.values())


def cls_bases(cls: Type) -> List[str]:
    return [b.__name__ for b in cls.__bases__]


_missing = object()


@singledispatch
def select_attrs(
    instance: object, attrs: Iterable[str], skip_none: bool = True
) -> Dict[str, object]:
    if skip_none:
        return {
            attr_name: attr_value
            for attr_name in attrs
            if (attr_value := getattr(instance, attr_name, None))
        }
    return {
        attr_name: getattr(instance, attr_name)
        for attr_name in attrs
        if getattr(instance, attr_name, _missing) is not _missing
    }


@select_attrs.register
def _select_attrs_from_dict(
    instance: dict, attrs: Iterable[str], skip_none: bool = True
) -> Dict[str, object]:
    if skip_none:
        return {
            attr_name: value
            for attr_name in attrs
            if (value := instance.get(attr_name, None))
        }
    return {attr_name: instance[attr_name] for attr_name in attrs}


KT = TypeVar("KT")
VT = TypeVar("VT")


def key_equal_value_to_dict(key_values: List[str]) -> Dict[str, str]:
    """
    >>> key_equal_value_to_dict(['a=b', 'b=c=d', 'c=lol'])
    {'a': 'b', 'b': 'c=d', 'c': 'lol'}

    :param key_values:
    :return:
    """
    return dict(
        name_equal_value.split("=", maxsplit=1) for name_equal_value in key_values
    )


def key_values(
    dict_object: Dict[KT, VT],
    key_filter: Callable[[KT], bool] = lambda _: True,
    value_filter: Callable[[VT], bool] = lambda _: True,
) -> Iterable[str]:
    return (
        f"{key}={value!r}" if isinstance(key, str) else f"{key!r}={value!r}"
        for key, value in dict_object.items()
        if key_filter(key) and value_filter(value)
    )


def transpose(d: Dict[KT, VT]) -> Dict[VT, KT]:
    """
    >>> transpose(dict(a=1, b=2))
    {1: 'a', 2: 'b'}
    """
    return dict(zip(d.values(), d.keys()))


def partition(
    iterable: Iterable[T], pred: Optional[Callable[[T], bool]] = None
) -> Tuple[List[T], List[T]]:
    """From more_iterutils Returns a 2-tuple of iterables derived from the
    input iterable. The first yields the items that have ``pred(item) ==
    False``. The second yields the items that have ``pred(item) == True``.

        >>> is_odd = lambda x: x % 2 != 0
        >>> iterable = range(10)
        >>> even_items, odd_items = partition(iterable, is_odd)
        >>> list(even_items), list(odd_items)
        ([0, 2, 4, 6, 8], [1, 3, 5, 7, 9])

    If *pred* is None, :func:`bool` is used.

        >>> iterable = [0, 1, False, True, '', ' ']
        >>> false_items, true_items = partition(iterable, None)
        >>> list(false_items), list(true_items)
        ([0, False, ''], [1, True, ' '])
    """
    if pred is None:
        pred = bool

    evaluations = ((pred(x), x) for x in iterable)
    t1, t2 = tee(evaluations)
    return [x for (cond, x) in t1 if not cond], [x for (cond, x) in t2 if cond]


def last(iterable: Iterable[T]) -> Optional[T]:
    """
    >>> last([1, 2, 3])
    3
    >>> last([])
    >>> last((1, 2, 3))
    3
    >>> last(range(1, 4))
    3
    """
    value = None
    for value in iterable:
        continue
    return value


def group_by_once(
    iterable: Iterable[VT], *, key=Callable[[VT], KT]
) -> dict[KT, list[VT]]:
    """
    >>> example = ["a", "b", "aa", "c"]
    >>> from itertools import groupby
    >>> [(key, list(iterable)) for key, iterable in groupby(example, key=len)]
    [(1, ['a', 'b']), (2, ['aa']), (1, ['c'])]
    >>> list(group_by_once(example, key=len).items())
    [(1, ['a', 'b', 'c']), (2, ['aa'])]
    """
    full = defaultdict(list)
    for instance in iterable:
        full[key(instance)].append(instance)
    return {**full}


@singledispatch
def _unpack(raw: object, allowed_falsy: set[object] | None):
    return raw


@_unpack.register
def _unpack_list(raw: list, allowed_falsy: set[object] | None):
    return [_unpack(each_raw, allowed_falsy) for each_raw in raw]


@_unpack.register
def _unpack_dict(raw: dict, allowed_falsy: set[object] | None):
    return ignore_falsy_recurse(**raw, allowed_falsy=allowed_falsy)


_allowed_falsy = {False, 0}


def ignore_falsy_recurse(allowed_falsy: set[object] | None = None, **kwargs) -> dict:
    """Ignores empty dictionaries or lists and None values.
    Warning:
        Keeps False & 0

    >>> ignore_falsy_recurse(a=0, b="ok", c=None)
    {'a': 0, 'b': 'ok'}
    >>> ignore_falsy_recurse(a=[{"name": "e", "age": None}, {"people": []}, {}], b="ok", c=None)
    {'a': [{'name': 'e'}, {}, {}], 'b': 'ok'}
    >>> ignore_falsy_recurse(a=[{"name": "e", "age": None}, {"people": [{"name": "nested", "lastname": ""}]}, {}], b="ok", c=None)
    {'a': [{'name': 'e'}, {'people': [{'name': 'nested'}]}, {}], 'b': 'ok'}
    """
    allowed_falsy = allowed_falsy or _allowed_falsy
    return {
        key: _unpack(value, allowed_falsy)
        for key, value in kwargs.items()
        if value or (not isinstance(value, (dict, list)) and value in allowed_falsy)
    }


def ignore_falsy(**kwargs) -> dict:
    """
    Warning: Also removes 0 or False
    >>> ignore_falsy(a=0, b="ok", c=None)
    {'b': 'ok'}
    """
    return {key: value for key, value in kwargs.items() if value}


def ignore_none(**kwargs) -> dict:
    return {key: value for key, value in kwargs.items() if value is not None}
