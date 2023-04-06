import string
from random import choices
from time import time
from typing import Tuple
from uuid import uuid4


def unique_id(length: int, character_class: str) -> str:
    """Returns a unique id of length `length`.

    A unique id is a string of length 1 or greater composed of
    characters from a character_class.
    For example, a unique id of length 6 composed of characters from the
    character class [0-9a-f] might be the following:

        a1fb32

    Different calls to `unique_id` are expected to return unequal unique ids. While we expect this
    to be true in most business relevant cases, it must be understood that this is not guaranteed
    and that, while generally improbable, a call to `unique_id` might return the exact same unique
    id as the precedent call.

    Different combinations of `length` and `character_class` modify the chance of a collision.

    For example, two successive calls of `unique_id` with a single element `character_class` are
    guaranteed to return the same unique id independently of the used length. Thus `unique_id``
    would guarantee a period of 1.

    More generally, two successive calls of `unique_id` with a `length` of 1 and a
    `character_class` composed of n characters have a probability of 1/n of returning the same
    unique id. Thus `unique_id` would have a maximum period of n that would not be guaranteed.

    A `length` of 5 with the character class [0-9a-f] would provide a maximum non guaranteed
    period of about 500000.

    A `character_class` should not contain any repeated character. Having characters that are
    repeated will increase the chance of a collision.

    `unique_id` should not directly be used in other parts of the codebase.

    Args:
        length: The length of the requested unique id. Must be a positive integer.
        character_class: The characters allowed in the unique id. Must contain at least one character.

    Raises:
        AssertionError when `length` is 0 or less.
        AssertionError when `character_class` is empty.

    Returns:
        A random string of length `length` composed only by characters contained in `character_clas`.
    """

    assert length > 0, "length must be a positive natural!"
    assert character_class, "character_class should contain at least one character!"

    return "".join(choices(character_class, k=length))


"""
A string containing all the characters that are available to be used in a GET query paramaters
without being escaped.

See https://www.456bereastreet.com/archive/201008/what_characters_are_allowed_unencoded_in_query_strings/
for informations about what characters are allowed.
"""
url_query_safe_characters: str = (
    string.ascii_letters + string.digits + "-_.!$&'()*+,;=:@?"
)


def url_safe_unique_id(length: int = 32) -> str:
    """Returns a unique id composed of characters that can be used in a GET
    query parameter.

    The `length` default value is a refuse of a previous iteration of this function and has no
    particular meaning.

    @see `url_query_safe_characters` to learn about the characters that are allowed.
    @see `unique_id` to learn about what a unique id is.

    Args:
       length: The length of the requested unique id.

    Raises:
        AssertionError when `length` is 0 or less.

    Returns:
        A unique id of length `length` composed of character that can be used to form a GET query
        parameter without being escaped.
    """

    return unique_id(length, url_query_safe_characters)


string_or_digit = string.ascii_letters + string.digits


def simple_id(length: int = 10) -> str:
    """
    >>> len(simple_id())
    10
    >>> simple_id() != simple_id()
    True
    """
    return "".join(choices(string_or_digit, k=length))


def uuid4_hex():
    return uuid4().hex


def ms_time_and_random(random_length: int = 5, separator: str = "-") -> str:
    """
    >>> ms_time_and_random() #doctest:+SKIP
    '1620244384.258-k7d3N'
    ''
    """
    return f"{time():.3f}{separator}{simple_id(random_length)}"


def as_ms_time_and_random(ms_time: str, separator: str = "-") -> Tuple[float, str]:
    """
    >>> as_ms_time_and_random('1620244384.258-k7d3N')
    (1620244384.258, 'k7d3N')
    >>> as_ms_time_and_random('1620244384.258-k7d3N', separator="+")
    Traceback (most recent call last):
    ...
    ValueError: not enough values to unpack (expected 2, got 1)
    >>> as_ms_time_and_random('1620244384K.258-k7d3N')
    Traceback (most recent call last):
    ...
    ValueError: could not convert string to float: '1620244384K.258'
    """
    time_str, random_str = ms_time.split(separator, maxsplit=1)
    return float(time_str), random_str
