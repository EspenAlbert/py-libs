from zero_3rdparty.iter_utils import public_values, unique_instance_iter, want_list


class NonSortedClassVars:
    c = "c"
    a = "a"
    b = "b"


def test_sort_public_values():
    actual = public_values(NonSortedClassVars)
    assert actual == ["a", "b", "c"]


def test_unique_instance_iter():
    a = object()
    b = object()
    c = object()
    assert list(unique_instance_iter([a, a, b, a, b, c])) == [a, b, c]


def test_want_list():
    before = [1, 2, 3]
    generator = want_list(before)
    after = list(generator)
    assert before == after


def test_want_list_from_single_value():
    before = 1
    generator = want_list(before)
    after = list(generator)
    assert [before] == after


def test_want_list_from_generator():
    generator = want_list((i for i in range(5)))
    after = list(generator)
    assert after == [0, 1, 2, 3, 4]


def test_want_list_from_generator_func():
    def a():
        for i in range(5):
            yield i

    generator = want_list(a())
    after = list(generator)
    assert after == [0, 1, 2, 3, 4]


def test_want_list_from_tuple():
    assert want_list((1, 2, 3)) == [1, 2, 3]
