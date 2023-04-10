from concurrent.futures import ThreadPoolExecutor

from zero_3rdparty.future import safe_wait, Future


def test_type_completion():
    def return_string() -> str:
        return "OK"

    with ThreadPoolExecutor() as executor:
        future: Future[str] = executor.submit(return_string)
        result = safe_wait(future)
        assert result == "OK"
