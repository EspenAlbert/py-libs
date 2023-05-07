from zero_3rdparty.object_name import as_name, func_arg_names


class MyClass:
    pass


def test_name_on_class():
    assert "test_zero_3rdparty.test_object_name.MyClass" == as_name(MyClass)


def test_name_on_instance():
    assert "test_zero_3rdparty.test_object_name.MyClass" == as_name(MyClass())


def func():
    pass


def test_name_on_func():
    assert as_name(func) == "test_zero_3rdparty.test_object_name.func"


async def async_func():
    pass


def test_name_on_async_func():
    assert as_name(async_func) == "test_zero_3rdparty.test_object_name.async_func"


def test_name_on_async_coroutine():
    assert as_name(async_func()) == "test_zero_3rdparty.test_object_name.async_func"


def test_func_arg_names_from_normal_func():
    def my_function_no_hints(a, b, c):
        return b

    assert func_arg_names(my_function_no_hints) == ["a", "b", "c"]


def test_func_arg_names_from_hinted_func():
    def my_function_with_hints(a: str, b: int, c: bool) -> int:
        return b

    assert func_arg_names(my_function_with_hints) == ["a", "b", "c"]


def test_func_arg_names_from_mixed_func():
    def my_function_mixed_hints(a, b: int, c: bool) -> int:
        return b

    assert func_arg_names(my_function_mixed_hints) == ["a", "b", "c"]
