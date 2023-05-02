import pytest
from zero_3rdparty.datetime_utils import date_filename


@pytest.mark.freeze_time("2020-01-01T08:34:22.124151")
def test_values_time_name():
    assert date_filename() == "2020-01-01T08-34Z"
