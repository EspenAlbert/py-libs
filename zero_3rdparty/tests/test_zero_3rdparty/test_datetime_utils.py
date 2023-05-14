from datetime import datetime, timedelta

import pytest
from zero_3rdparty.datetime_utils import (
    as_day_name,
    date_filename,
    date_filename_with_seconds,
    dump_as_kub_time,
    ensure_tz,
    ms_between,
    parse_date_filename_with_seconds,
    utc_now_ms_precision,
    week_nr,
)


@pytest.mark.freeze_time("2020-01-01T08:34:22.124151")
def test_values_time_name():
    assert date_filename() == "2020-01-01T08-34Z"


def test_week_nr():
    week_52_dt = datetime(2023, 1, 1)
    day_name = as_day_name(week_52_dt)
    assert day_name == "Sunday"
    assert week_nr(week_52_dt) == 52
    assert week_nr(week_52_dt + timedelta(days=1)) == 1


def test_as_ms_precision_utc():
    dt = utc_now_ms_precision()
    assert dt.microsecond % 1000 == 0


def test_ensure_tz():
    pass


def test_date_filename_with_seconds():
    dt = parse_date_filename_with_seconds("2021-04-07T08-46-02")
    assert date_filename_with_seconds(dt) == "2021-04-07T08-46-02"
    dt2 = parse_date_filename_with_seconds("2021-04-07T08-46-03")
    assert date_filename_with_seconds(dt2) == "2021-04-07T08-46-03"
    assert ms_between(dt, dt2) == 1000

    no_timezone = dt2.replace(tzinfo=None)
    assert dump_as_kub_time(no_timezone) == "2021-04-07T08:46:03"
    dt3 = ensure_tz(no_timezone)
    assert dump_as_kub_time(dt3) == "2021-04-07T08:46:03Z"
