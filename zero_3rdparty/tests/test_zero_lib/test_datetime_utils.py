import time

import pytest
from zero_3rdparty.datetime_utils import date_filename, utc_now_ms_precision


@pytest.mark.freeze_time("2020-01-01T08:34:22.124151")
def test_values_time_name():
    assert date_filename() == "2020-01-01T08-34Z"


def test_utc_now_ms():
    prev_date = utc_now_ms_precision()
    time.sleep(0.1)
    now = utc_now_ms_precision()
    assert prev_date <= now
