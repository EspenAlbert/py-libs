import os
import re
import reprlib
import sys
from functools import singledispatch
from typing import (
    Any,
    AnyStr,
    Callable,
    Iterable,
    List,
    Optional,
    Pattern,
    Set,
    TextIO,
    Union,
)

from zero_3rdparty.iter_utils import key_values, select_attrs


def words_to_list(
    s: str,
    split_char: str = " ",
    alternative_split_char: Optional[str] = None,
    skip_strip: bool = False,
) -> List[str]:
    """
    >>> words_to_list("a b c")
    ['a', 'b', 'c']
    >>> words_to_list('a b,c')
    ['a', 'b,c']
    >>> words_to_list('a b,c', alternative_split_char=',')
    ['a', 'b', 'c']
    >>> words_to_list('a  b    c')
    ['a', 'b', 'c']
    >>> words_to_list("a  b    c", skip_strip=True)
    ['a', '', 'b', '', '', '', 'c']
    """
    s = (
        s
        if alternative_split_char is None
        else s.replace(alternative_split_char, split_char)
    )
    return [
        part if skip_strip else part.strip()
        for part in s.split(split_char)
        if skip_strip or part.strip()
    ]


def words_to_set(s: str, split_char: str = " ") -> Set[str]:
    """
    >>> sorted(words_to_set("word1 word2 word3"))
    ['word1', 'word2', 'word3']
    """
    return set(s.split(split_char))


def want_str(s: AnyStr, encoding: str = "utf-8") -> str:
    """
    >>> want_str(b"hello")
    'hello'
    >>> want_str("hello")
    'hello'
    """
    if isinstance(s, bytes):
        return s.decode(encoding=encoding)
    return s


def want_bytes(s: AnyStr, encoding: str = "utf-8") -> bytes:
    """Convert string to bytes.
    >>> want_bytes(b"hello")
    b'hello'
    >>> want_bytes("hello")
    b'hello'
    """
    if isinstance(s, str):
        return s.encode(encoding=encoding)
    return s


@singledispatch
def want_bool(s: Union[str, bool, None]) -> bool:
    """
    >>> want_bool("False")
    False
    >>> want_bool("True")
    True
    >>> want_bool(True)
    True
    >>> want_bool(1)
    True
    >>> want_bool(0)
    False
    >>> want_bool(22)
    Traceback (most recent call last):
    ...
    ValueError: int value=22 not 0 or 1
    >>> want_bool(object())
    Traceback (most recent call last):
    ...
    NotImplementedError: object
    """
    raise NotImplementedError(type(s).__name__)


@want_bool.register
def _want_bool_str(s: str) -> bool:
    return s.strip().lower() in {"true", "1", "yes", "t"}


@want_bool.register
def _want_bool_bool(s: bool) -> bool:
    return s


@want_bool.register
def _want_bool_int(s: int) -> bool:
    if s == 0:
        return False
    if s == 1:
        return True
    raise ValueError(f"int value={s} not 0 or 1")


@want_bool.register
def _want_bool_none(s: None) -> bool:
    return False


def filename_to_title(filename: str) -> str:
    """
    >>> filename_to_title('/Users/espen/source/writings/software/04_writing_docs.md')
    'Writing Docs'
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


class NoMatchError(ValueError):
    def __init__(self, raw: str, pattern: str):
        super().__init__(f"pattern={pattern} did not match={raw}")
        self.raw = raw
        self.pattern = pattern


def group_dict_or_match_error(re_str: str) -> Callable[[str], dict]:
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
