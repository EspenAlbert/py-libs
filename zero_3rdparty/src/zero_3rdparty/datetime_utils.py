"""https://docs.python.org/3/library/datetime.html#strftime-and-strptime-
format-codes."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from functools import singledispatch
from typing import TypeVar


def get_date_as_rfc3339_without_time(date: datetime | None = None) -> str:
    """
    >>> len(get_date_as_rfc3339_without_time()) == len('2019-08-14')
    True

    :param date:
    :return:
    """
    if date is None:
        date = datetime.now(tz=timezone.utc)
    return date.astimezone(timezone.utc).isoformat()[:10]


@singledispatch
def dump_date_as_rfc3339(
    date: datetime | float | None, strip_microseconds=False
) -> str:
    """
    >>> dump_date_as_rfc3339(datetime(2018, 9, 12, 1, 57, 54, 494142, tzinfo=timezone.utc))
    '2018-09-12T01:57:54.494142+00:00'
    >>> len(dump_date_as_rfc3339(None, strip_microseconds=True)) == len('2019-08-14T05:11:42+00:00')
    True
    """
    raise NotImplementedError


@dump_date_as_rfc3339.register
def _dump_date_as_rfc3339_date(date: datetime, strip_microseconds: bool = False) -> str:
    if strip_microseconds:
        date = date.replace(microsecond=0)
    return date.astimezone(timezone.utc).isoformat()


@dump_date_as_rfc3339.register
def _dump_date_as_rfc3339_none(
    date: None = None, strip_microseconds: bool = False
) -> str:
    return _dump_date_as_rfc3339_date(datetime.now(tz=timezone.utc), strip_microseconds)


@dump_date_as_rfc3339.register
def _dump_date_as_rfc3339_float(date: float, strip_microseconds: bool = False) -> str:
    dt = datetime.fromtimestamp(date, tz=timezone.utc)
    return _dump_date_as_rfc3339_date(dt, strip_microseconds)


def utc_now():
    return datetime.now(tz=timezone.utc)


def week_nr(dt: datetime) -> int:
    return dt.isocalendar()[1]


def as_ms_precision_utc(dt: datetime) -> datetime:
    old_microseconds = dt.microsecond
    new_microseconds = str(old_microseconds)[:3] + "000"
    return dt.replace(microsecond=int(new_microseconds), tzinfo=timezone.utc)


def utc_now_ms_precision() -> datetime:
    return as_ms_precision_utc(utc_now())


def ms_between(start: datetime, end: datetime | None = None) -> float:
    end = end or utc_now()
    return (end.timestamp() - start.timestamp()) * 1000


def seconds_between_safe(start: datetime, end: datetime) -> float:
    """
    >>> seconds_between_safe(datetime(2020, 1, 1, 1), datetime(2020, 1, 1, 2))
    3600.0
    >>> seconds_between_safe(datetime(2020, 1, 1, 1), datetime(2020, 1, 1, 2, tzinfo=timezone.utc))
    3600.0
    """
    start = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
    end = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
    return (end - start).total_seconds()


def ensure_tz(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_kub_time(raw: str) -> datetime:
    """
    >>> parse_kub_time("2020-08-29T07:35:12Z")
    datetime.datetime(2020, 8, 29, 7, 35, 12, tzinfo=datetime.timezone.utc)
    >>> parse_kub_time('2021-04-23T18:15:12.383442Z')
    datetime.datetime(2021, 4, 23, 18, 15, 12, 383442, tzinfo=datetime.timezone.utc)
    >>> parse_kub_time('2021-04-23T18:15:12.3834422Z')
    datetime.datetime(2021, 4, 23, 18, 15, 12, 383442, tzinfo=datetime.timezone.utc)
    """
    if "." in raw:
        before_decimal, decimal_part = raw.rsplit(".", maxsplit=1)
        if len(decimal_part.rstrip("Z")) > 6:
            raw = f"{before_decimal}.{decimal_part[:6]}Z"
    return datetime.fromisoformat(raw.replace("T", " ").replace("Z", "+00:00"))


@singledispatch
def want_dt(dt: object) -> datetime:
    raise NotImplementedError


@want_dt.register
def _from_date(dt: date):
    return datetime(year=dt.year, month=dt.month, day=dt.day, tzinfo=timezone.utc)


@want_dt.register
def _from_datetime(dt: datetime):
    return dt


@want_dt.register
def _from_int(dt: int):
    return datetime.fromtimestamp(dt, tz=timezone.utc)


@want_dt.register
def _from_str(dt: str):
    return datetime.fromisoformat(dt)


def dump_as_kub_time(dt: datetime | date | int | str) -> str:
    """
    >>> dump_as_kub_time(datetime(2020, 8, 29, 7, 35, 12, tzinfo=timezone.utc))
    '2020-08-29T07:35:12Z'
    >>> dump_as_kub_time(date(2020, 8, 29))
    '2020-08-29T00:00:00Z'
    >>> dump_as_kub_time(1703480465)
    '2023-12-25T05:01:05Z'
    >>> dump_as_kub_time("2023-12-25T05:01:10+00:00")
    '2023-12-25T05:01:10Z'
    """
    dt = want_dt(dt)
    return dt.isoformat(sep="T").replace("+00:00", "Z")


def date_filename(dt: datetime | None = None) -> str:
    """
    Example: 2020-03-16T17-52Z
    """
    dt = dt or utc_now()
    return (
        dt.isoformat(sep="T", timespec="minutes")
        .replace("+00:00", "Z")
        .replace(":", "-")
    )


def date_filename_with_seconds(dt: datetime | None = None) -> str:
    """
    >>> date_filename_with_seconds(datetime(year=2023, month=5, day=2, hour=9, minute=4, tzinfo=timezone.utc))
    '2023-05-02T09-04-00'
    >>> date_filename_with_seconds(datetime(year=2023, month=5, day=2, hour=9, minute=4))
    '2023-05-02T09-04-00'
    """
    dt = dt or utc_now()
    seconds = dt.second
    filename = date_filename(dt)
    return filename.removesuffix("Z") + f"-{seconds:02}"


def iso_format_truncate_to_seconds(dt: datetime) -> str:
    """
    >>> iso_format_truncate_to_seconds(datetime(year=2023, month=5, day=2, hour=9, minute=4, tzinfo=timezone.utc))
    '2023-05-02T09:04:00'
    """
    return dt.isoformat(timespec="seconds").removesuffix("+00:00")


def parse_date_filename_with_seconds(raw: str) -> datetime:
    """
    >>> parse_date_filename_with_seconds('2021-04-07T08-46-02')
    datetime.datetime(2021, 4, 7, 8, 46, 2, tzinfo=datetime.timezone.utc)
    """
    return datetime.strptime(raw, "%Y-%m-%dT%H-%M-%S").replace(tzinfo=timezone.utc)


def as_day_name(dt: datetime | date) -> str:
    return dt.strftime("%A")


_WEEKEND_DAYS = {5, 6}


@singledispatch
def is_weekend(dt: object) -> bool:
    """
    >>> sun = datetime(2023, month=1, day=22)
    >>> as_day_name(sun)
    'Sunday'
    >>> is_weekend(sun)
    True
    >>> from datetime import timedelta
    >>> sat = sun - timedelta(days=1)
    >>> as_day_name(sat)
    'Saturday'
    >>> is_weekend(sat)
    True
    >>> is_weekend(sat - timedelta(days=1))
    False
    >>> is_weekend('Saturday')
    True
    >>> is_weekend('Friday')
    False
    """
    raise NotImplementedError


@is_weekend.register
def _from_dt(dt: datetime) -> bool:
    return dt.weekday() in _WEEKEND_DAYS


_now = utc_now()
_day_mapping = {
    as_day_name(dt): dt.weekday()
    for add_day in range(7)
    if (dt := _now + timedelta(days=add_day))
}


@is_weekend.register
def _is_weekend_str(dt: str):
    return _day_mapping[dt] in _WEEKEND_DAYS


def month_range(dt: datetime):
    """
    >>> month_range(datetime(year=2023, month=1, day=22))
    (datetime.datetime(2023, 1, 1, 0, 0), datetime.datetime(2023, 2, 1, 0, 0))
    >>> month_range(datetime(year=2022, month=12, day=22))
    (datetime.datetime(2022, 12, 1, 0, 0), datetime.datetime(2023, 1, 1, 0, 0))
    >>> # how to get the last microsecond of the month
    >>> from datetime import timedelta
    >>> end_of_month = month_range(datetime(year=2022, month=12, day=22))[1] - timedelta(microseconds=1)
    >>> end_of_month
    datetime.datetime(2022, 12, 31, 23, 59, 59, 999999)
    >>> end_of_month.year
    2022
    """
    start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        start_next_month = start.replace(year=start.year + 1, month=1)
    else:
        start_next_month = start.replace(month=start.month + 1)
    return start, start_next_month


DT = TypeVar("DT", bound=date)


def day_range(start: DT, end: DT, delta: timedelta) -> Iterable[DT]:
    """
    >>> start = datetime(year=2023, month=1, day=1)
    >>> end = datetime(year=2023, month=1, day=10)
    >>> day: DT
    >>> [day.day for day in day_range(start, end, timedelta(days=1))]
    [1, 2, 3, 4, 5, 6, 7, 8, 9]
    """
    steps = int((end - start) / delta)
    for index in range(steps):
        yield start + (delta * index)


def day_ranges(start: DT, end: DT, delta: timedelta) -> Iterable[tuple[DT, DT]]:
    """Returns a [(start1, end1), (start2, end2)] where end1==start2.

    >>> start = datetime(year=2023, month=1, day=1)
    >>> end = datetime(year=2023, month=1, day=11)
    >>> [(dt_i.day, dt_j.day) for dt_i, dt_j in day_ranges(start, end, timedelta(days=5))]
    [(1, 6), (6, 11)]
    >>> [(dt_i.day, dt_j.day) for dt_i, dt_j in day_ranges(start, end.replace(day=10), timedelta(days=5))]
    [(1, 6)]
    """
    for next_dt in day_range(start, end, delta):
        next_dt_end = next_dt + delta
        if next_dt_end > end:
            break
        yield next_dt, next_dt_end


def week_dt(year: int, week: int) -> datetime:
    """
    >>> week_dt(2023, 1)
    datetime.datetime(2023, 1, 2, 0, 0, tzinfo=datetime.timezone.utc)
    >>> week_dt(2023, 18)
    datetime.datetime(2023, 5, 1, 0, 0, tzinfo=datetime.timezone.utc)
    """
    jan_1st = datetime(year, 1, 1, tzinfo=timezone.utc)
    start_monday = jan_1st - timedelta(days=jan_1st.weekday())
    if week_nr(start_monday) != 1:
        start_monday += timedelta(weeks=1)
    return start_monday + timedelta(weeks=week - 1)


def prev_monday(weeks: int = 0) -> datetime:
    """
    >>> prev_monday().weekday()
    0
    >>> prev_monday(weeks=1).weekday()
    0
    >>> prev_monday() != prev_monday(weeks=1)
    True
    >>> prev_monday().strftime("%H:%M:%S")
    '00:00:00'

    """
    today = utc_now()
    monday = today - timedelta(days=today.weekday(), weeks=weeks)
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)
