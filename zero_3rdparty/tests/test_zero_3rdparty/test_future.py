from concurrent.futures import ThreadPoolExecutor

from zero_3rdparty.future import Future, safe_wait


def test_type_completion():
    def return_string() -> str:
        return "OK"

    def return_string_by_arg(a: str) -> str:
        return a

    with ThreadPoolExecutor() as executor:
        future: Future[str] = executor.submit(return_string)
        result = safe_wait(future)
        assert result == "OK"

        future2: Future[str] = executor.submit(return_string_by_arg, "OK2")
        result2 = safe_wait(future2)
        assert result2 == "OK2"
