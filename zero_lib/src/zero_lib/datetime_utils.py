"""https://docs.python.org/3/library/datetime.html#strftime-and-strptime-
format-codes."""
from datetime import date, datetime, timedelta, timezone
from functools import singledispatch
from typing import Iterable, Optional, TypeVar, overload


def get_date_as_rfc3339_without_time(date: datetime = None) -> str:
    """
    >>> len(get_date_as_rfc3339_without_time()) == len('2019-08-14')
    True

    :param date:
    :return:
    """
    if date is None:
        date = datetime.now(tz=timezone.utc)
    return date.astimezone(timezone.utc).isoformat()[:10]


def get_date_as_rfc3339(date: datetime = None, strip_microseconds=False) -> str:
    """
    >>> get_date_as_rfc3339(datetime(2018, 9, 12, 1, 57, 54, 494142, tzinfo=timezone.utc))
    '2018-09-12T01:57:54.494142+00:00'
    >>> len(get_date_as_rfc3339(strip_microseconds=True)) == len('2019-08-14T05:11:42+00:00')
    True

    :param date:
    :return:
    """
    if date is None:
        date = datetime.now(tz=timezone.utc)
    if strip_microseconds:
        date = date.replace(microsecond=0)
    return date.astimezone(timezone.utc).isoformat()


def utc_now():
    return datetime.now(tz=timezone.utc)


def week_nr(dt: datetime) -> int:
    return dt.isocalendar()[1]


def as_ms_precision_utc(dt: datetime) -> datetime:
    old_microseconds = dt.microsecond
    new_microseconds = str(old_microseconds)[:3] + "000"
    return dt.replace(microsecond=int(new_microseconds), tzinfo=timezone.utc)


def utc_now_ms_precision():
    return as_ms_precision_utc(utc_now())


def ms_between(start: datetime, end: Optional[datetime] = None) -> float:
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


def dump_as_kub_time(dt: datetime) -> str:
    """
    >>> dump_as_kub_time(datetime(2020, 8, 29, 7, 35, 12, tzinfo=timezone.utc))
    '2020-08-29T07:35:12Z'
    """
    return dt.isoformat(sep="T").replace("+00:00", "Z")


def date_filename(dt: Optional[datetime] = None) -> str:
    """
    Example: 2020-03-16T17-52Z
    """
    dt = dt or utc_now()
    return (
        dt.isoformat(sep="T", timespec="minutes")
        .replace("+00:00", "Z")
        .replace(":", "-")
    )


def date_filename_with_seconds(dt: Optional[datetime] = None) -> str:
    """
    Example: 2021-04-07T08-46-02
    """
    dt = dt or utc_now()
    seconds = dt.second
    filename = date_filename(dt)
    return filename[:-1] + f"-{seconds:02}"


def parse_date_filename_with_seconds(raw: str) -> datetime:
    """
    >>> parse_date_filename_with_seconds('2021-04-07T08-46-02')
    datetime.datetime(2021, 4, 7, 8, 46, 2, tzinfo=datetime.timezone.utc)
    """
    return datetime.strptime(raw, "%Y-%m-%dT%H-%M-%S").replace(tzinfo=timezone.utc)


def as_day_name(dt: datetime | date) -> str:
    return dt.strftime("%A")


_WEEKEND_DAYS = {5, 6}


@overload
def is_weekend(dt: str) -> bool:
    ...


@singledispatch
def is_weekend(dt: datetime) -> bool:
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
    >>> month_range(datetime(year=2022, month=12, day=22))[1] - timedelta(microseconds=1)
    datetime.datetime(2022, 12, 31, 23, 59, 59, 999999)
    >>> _.year
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
    >>> [day.day for day in day_range(start, end, timedelta(days=1))]
    [1, 2, 3, 4, 5, 6, 7, 8, 9]
    """
    steps = int((end - start) / delta)
    for index in range(steps):
        yield start + (delta * index)
