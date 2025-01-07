import pytest

from zero_3rdparty.str_utils import NoMatchError, group_dict_or_match_error, want_bool

log_pattern = r"\[(?P<ts>\S+)" r"\s+" r"(?P<log_level>\w+)" r"\]\s?" r"(?P<message>.*)"

fleet_str = """[2021-06-25T04:13:10Z INFO] my-message-1"""
fleet_str2 = """[2021-06-29T15:29:31Z INFO] some other message"""


def test_group_dict_or_match_error():
    assert group_dict_or_match_error(log_pattern)(fleet_str) == {
        "log_level": "INFO",
        "message": "my-message-1",
        "ts": "2021-06-25T04:13:10Z",
    }
    assert group_dict_or_match_error(log_pattern)(fleet_str2) == {
        "log_level": "INFO",
        "message": "some other message",
        "ts": "2021-06-29T15:29:31Z",
    }
    with pytest.raises(NoMatchError):
        group_dict_or_match_error(log_pattern)("some nonmatching str")


@pytest.mark.parametrize("valid_true_bool", ["t ", "True", " TRUE", "yes", "1"])
def test_want_bool_true(valid_true_bool):
    assert want_bool(valid_true_bool)


@pytest.mark.parametrize("valid_false_bool", ["f ", "false", "no", "", None])
def test_want_bool_false(valid_false_bool):
    assert want_bool(valid_false_bool) is False
