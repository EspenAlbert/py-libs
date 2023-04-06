from dataclasses import dataclass
from time import sleep

import pytest
from zero_lib.cache_ttl import cache_ttl, clear_cache

SLEEP_TIME = 0.01
TOTAL_RUNTIME = 0.30


@pytest.mark.parametrize(
    "cache_time, expected_max_length", ((0.1, 4), (0.4, 1), (0.2, 2))
)
def test_cache_ttl(cache_time, expected_max_length):
    _current_count = 0

    @cache_ttl(cache_time)
    def counter():
        nonlocal _current_count
        print("counter called")
        _current_count += 1
        return _current_count

    values = call_cached_function(counter)
    assert len(values) <= expected_max_length


def call_cached_function(func):
    values: set[int] = set()
    for i in range(round(TOTAL_RUNTIME / SLEEP_TIME)):
        result = func()
        time = i * SLEEP_TIME
        print(f"result @ {time:.2f}s = {result}")
        values.add(result)
        sleep(SLEEP_TIME)
    return values


def create_cls_instances():
    @dataclass
    class MyClass:
        counter: int = 0

        @cache_ttl(0.1)
        def count(self) -> int:
            self.counter += 1
            return self.counter

    return MyClass(), MyClass(counter=10)


def test_test_cache_ttl_on_method():
    instance, instance2 = create_cls_instances()

    def call_both_instances():
        return instance.count(), instance2.count()

    values = call_cached_function(call_both_instances)
    assert all(r1 != r2 for r1, r2 in values)
    assert len({r1 for r1, _ in values}) <= 4
    assert len({r2 for _, r2 in values}) <= 4


def test_clearing_cache_on_func():
    _current_count = 0

    @cache_ttl(1)
    def counter() -> int:
        nonlocal _current_count
        _current_count += 1
        return _current_count

    assert counter() == 1
    assert counter() == 1
    clear_cache(counter)
    assert counter() == 2


def test_clearing_cache_on_meth():
    i1, i2 = create_cls_instances()
    assert (i1.count(), i2.count()) == (1, 11)
    clear_cache(i1.count)
    assert (i1.count(), i2.count()) == (2, 12)
