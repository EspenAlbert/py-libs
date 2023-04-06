import os
import re
import reprlib
import sys
from functools import singledispatch
from typing import Any, AnyStr, Callable, Iterable, List, Pattern, Set, TextIO

from zero_lib.iter_utils import key_values, select_attrs


def words_to_list(s: str, split_char: str = " ") -> List[str]:
    return list(s.split(split_char))


def words_to_set(s: str, split_char: str = " ") -> Set[str]:
    return set(s.split(split_char))


def want_str(s: AnyStr, encoding: str = "utf-8") -> str:
    """Convert bytes to string."""
    if isinstance(s, bytes):
        return s.decode(encoding=encoding)
    return s


def want_bytes(s: AnyStr, encoding: str = "utf-8") -> bytes:
    """Convert string to bytes."""
    if isinstance(s, str):
        return s.encode(encoding=encoding)
    return s


@singledispatch
def want_bool(s: str | bool) -> bool:
    """
    >>> want_bool("False")
    False
    >>> want_bool("True")
    True
    """
    return s.lower() in {"true", "1", "yes"}


@want_bool.register
def _want_bool_bool(s: bool) -> bool:
    return s


@want_bool.register
def _want_bool_none(s: None) -> bool:
    return False


def filename_to_beautiful_name(filename: str) -> str:
    """
    >>> filename_to_beautiful_name('/Users/espen/workspace/ea_code/docs/source/writings/software/04_writing_docs.md')
    'Writing Docs'

    :param filename:
    :return:
    """
    filename, _ = os.path.splitext(os.path.basename(filename))
    words_in_filename = re.findall(
        r"[\w]+", filename.replace("_", " ").replace("-", " ")
    )
    return " ".join(
        word.capitalize() for word in words_in_filename if re.search(r"[a-z]", word)
    )


def has_substr(s: str, substrings: Iterable[str], allow_string: bool = False) -> bool:
    """
    >>> APP_READY_LOG_MESSAGES = ["[^Worker]: Ready ", "is waiting"]
    >>> has_substr('RosBackend is waiting', APP_READY_LOG_MESSAGES)
    True
    >>> has_substr('RosBackend is not ready', APP_READY_LOG_MESSAGES)
    False
    """
    if not allow_string and isinstance(substrings, str):
        raise ValueError(f"str as substring not allowed {substrings!r}")
    return any(expected_ready in s for expected_ready in substrings)


def next_substr(s: str, substrings: Iterable[str]) -> Iterable[str]:
    """
    >>> APP_READY_LOG_MESSAGES = ["[^Worker]: Ready ", "is waiting"]
    >>> list(next_substr('RosBackend is waiting', APP_READY_LOG_MESSAGES))
    ['is waiting']
    """
    for substring in substrings:
        if substring in s:
            yield substring


def print_object(obj: Any, attrs: Iterable[str]) -> str:
    args = ", ".join(f"{key}={getattr(obj, key)!r}" for key in attrs)
    return f"{type(obj).__name__}({args})"


def print_as_table(d: dict, column_key_width=30, column_value_width=30) -> str:
    paths = sorted(
        f"{key}".ljust(column_key_width) + f"{d[key]}".ljust(column_value_width)
        for key in d
    )
    return "\n".join(paths)


def print_as_table_value_first(
    d: dict, column_key_width=30, column_value_width=30
) -> str:
    paths = sorted(
        f"{d[key]}".ljust(column_value_width) + f"{key}".ljust(column_key_width)
        for key in d
    )
    return "\n".join(paths)


ansi_escape = re.compile(
    r"""
    \x1B  # ESC
    (?:   # 7-bit C1 Fe (except CSI)
        [@-Z\\-_]
    |     # or [ for CSI, followed by a control sequence
        \[
        [0-?]*  # Parameter bytes
        [ -/]*  # Intermediate bytes
        [@-~]   # Final byte
    )
""",
    re.VERBOSE,
)


def remove_ansi_formatting(raw: str) -> str:
    """https://stackoverflow.com/questions/14693701/how-can-i-remove-the-ansi-
    escape-sequences-from-a-string-in-python."""
    return ansi_escape.sub("", raw)


fleet_pattern = (
    r"\[(?P<ts>\S+)"
    r"\s+"
    r"(?P<log_level>\w+)"
    r"\s+"
    r"(?P<fleet_group>[^\]]+)"
    r"\]\s?"
    r"(?P<message>.*?)"
    r"(elapsed:\s)?"
    r"(?P<query_elapsed>\d+\.\d+)"
    r"(?P<query_unit>\w+)"
    r"\s*"
    r"(?P<sql_query>.*)"
)

fleet_str = """[2021-06-25T04:13:10Z INFO  sqlx::query] SELECT schedule_id, fleet_id, scheduled_time \u2026; rows: 0, elapsed: 1.054ms SELECT schedule_id, fleet_id, scheduled_time FROM scheduled_missions WHERE ( executed_at IS NULL OR executed_at < (now() at time zone 'utc') :: date ) AND scheduled_time < (now() at time zone 'utc') :: time"""
fleet_str2 = """[2021-06-29T15:29:31Z INFO  sqlx::query] LISTEN "message_enqueued";; rows: 0, elapsed: 651.274µs"""


class NoMatchError(ValueError):
    def __init__(self, raw: str, pattern: str):
        super().__init__(f"pattern={pattern} did not match={raw}")
        self.raw = raw
        self.pattern = pattern


def group_dict_or_match_error(re_str: str) -> Callable[[str], dict]:
    """
    >>> group_dict_or_match_error(fleet_pattern)(fleet_str)
    {'ts': '2021-06-25T04:13:10Z', 'log_level': 'INFO', 'fleet_group': 'sqlx::query', 'message': 'SELECT schedule_id, fleet_id, scheduled_time …; rows: 0, ', 'query_elapsed': '1.054', 'query_unit': 'ms', 'sql_query': "SELECT schedule_id, fleet_id, scheduled_time FROM scheduled_missions WHERE ( executed_at IS NULL OR executed_at < (now() at time zone 'utc') :: date ) AND scheduled_time < (now() at time zone 'utc') :: time"}
    >>> group_dict_or_match_error(fleet_pattern)(fleet_str2)
    {'ts': '2021-06-29T15:29:31Z', 'log_level': 'INFO', 'fleet_group': 'sqlx::query', 'message': 'LISTEN "message_enqueued";; rows: 0, ', 'query_elapsed': '651.274', 'query_unit': 'µs', 'sql_query': ''}
    >>> group_dict_or_match_error(fleet_pattern)("some nonmatching str")
    Traceback (most recent call last):
    ...
    str_utils.NoMatchError: pattern=\[(?P<ts>\S+)\s+(?P<log_level>\w+)\s+(?P<fleet_group>[^\]]+)\]\s?(?P<message>.*?)(elapsed:\s)?(?P<query_elapsed>\d+\.\d+)(?P<query_unit>\w+)\s*(?P<sql_query>.*) did not match some nonmatching str # noqa: W605
    """
    pattern: Pattern = re.compile(re_str)

    def as_dict(raw: str) -> dict:
        match = pattern.match(raw)
        if not match:
            raise NoMatchError(raw, pattern=re_str)
        return match.groupdict()

    return as_dict


def instance_repr(
    instance: object, keys: Iterable[str], ignore_falsy: bool = True
) -> str:
    assert not isinstance(keys, str), "keys cannot be a single str"
    type_name = type(instance).__name__
    attrs = ",".join(key_values(select_attrs(instance, keys, skip_none=ignore_falsy)))
    return f"{type_name}({attrs})"


def only_alphabetical_or_space(raw: str) -> str:
    """
    >>> only_alphabetical_or_space("Stoic Six Pack - Meditations of Marcus Aurelius, Golden Sayings, Fragments and Discourses of Epictetus, Letters From A Stoic and The Enchiridion (Illustrated) ")
    'Stoic Six Pack  Meditations of Marcus Aurelius Golden Sayings Fragments and Discourses of Epictetus Letters From A Stoic and The Enchiridion Illustrated '
    """
    return "".join(c for c in raw if c.isalpha() or c.isspace())


def join_messages(a: str, b: str, sep: str = " ") -> str:
    """
    >>> join_messages("some start ", " some finish")
    'some start some finish'
    """
    return sep.join([a.rstrip(sep), b.lstrip(sep)])


def skip_lines(lines: str, skip_parts: List[str]) -> str:
    """
    >>> skip_lines("line1\\nout2\\nline2", ["out"])
    'line1\\nline2'
    """
    return "".join(
        line
        for line in lines.splitlines(keepends=True)
        if all(skip_part not in line for skip_part in skip_parts)
    )


_long_string = "some-very-long-merryh-piece-of-text-that-has-an-end"


def reduce_len(message_value: AnyStr) -> AnyStr:
    """
    >>> reduce_len(_long_string)
    'some-very-lo[...]t-has-an-end'
    """
    total_length = len(message_value)
    one_fourth = total_length // 4
    return message_value[:one_fourth] + "[...]" + message_value[-one_fourth:]


def ensure_within_len(msg: str, max_length: int, truncator="...") -> str:
    """
    >>> ensure_within_len("123456789", max_length=8)
    '12345...'
    >>> ensure_within_len("123456789", max_length=9)
    '123456789'
    """
    if len(msg) <= max_length:
        return msg
    return msg[: max_length - len(truncator)] + truncator


def write_to_stream_safely(text: str, stream: TextIO) -> None:
    if not text.endswith("\n"):
        text += "\n"
    try:
        stream.write(text)
        stream.flush()
    # ValueError: I/O operation on closed file.
    except ValueError as e:
        sys.stderr.write(f"stream_closed? {e!r}")


def instance_repr_long_str(
    instance: object, *, str_len: int = 1000, replace_line_breaks: bool = True
) -> str:
    """
    >>> instance_repr_long_str(dict(a=1, b="\\n".join(f"long-str-with-linebreaks-{i}" for i in range(10))))
    "{'a': 1, 'b': 'long-str-with-linebreaks-0\\nlong-str-with-linebreaks-1\\nlong-str-with-linebreaks-2\\nlong-str-with-linebreaks-3\\nlong-str-with-linebreaks-4\\nlong-str-with-linebreaks-5\\nlong-str-with-linebreaks-6\\nlong-str-with-linebreaks-7\\nlong-str-with-linebreaks-8\\nlong-str-with-linebreaks-9'}"
    """
    model_repr = reprlib.Repr()
    model_repr.maxstring = str_len
    model_str = model_repr.repr(instance)
    return model_str.replace(r"\n", "\n") if replace_line_breaks else model_str


def ensure_prefix(original: str, startswith: str) -> str:
    """
    >>> ensure_prefix("my-topic", startswith='test_')
    'test_my-topic'
    >>> ensure_prefix("test_my-topic", startswith='test_')
    'test_my-topic'
    """
    return startswith + original.removeprefix(startswith)


def ensure_suffix(original: str, endswith: str) -> str:
    """
    >>> ensure_suffix("my_file", ".txt")
    'my_file.txt'
    >>> ensure_suffix("my_file.txt", ".txt")
    'my_file.txt'
    """
    return original.removesuffix(endswith) + endswith
