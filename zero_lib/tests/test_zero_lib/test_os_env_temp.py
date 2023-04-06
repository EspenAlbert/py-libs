import os

from zero_lib.env_temp import os_env_temp


def test_temp_var_from_dict():
    d = dict(a="2", b="3")
    assert os.environ.get("a") is None
    with os_env_temp.from_dict(d):
        assert os.environ.get("a") == "2"
        assert os.environ.get("b") == "3"
    assert os.environ.get("a") is None
