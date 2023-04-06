from base64 import b64decode, b64encode
from functools import singledispatch
from secrets import token_bytes
from typing import Any, Final, Literal

# See https://tools.ietf.org/html/rfc3548.html
BASE64_CHARACTER_SET: Final[
    Literal["ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="]
] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="


@singledispatch
def encode_base64(b: str | bytes) -> str:
    raise NotImplementedError


@encode_base64.register
def encode_base64_str(b: bytes) -> str:
    return b64encode(b).decode("utf-8")


@encode_base64.register
def encode_base64_str(s: str) -> str:
    """
    >>> encode_base64('default:default')
    'ZGVmYXVsdDpkZWZhdWx0'

    :param s:
    :return:
    """
    b = s.encode(encoding="utf-8")
    return b64encode(b).decode("utf-8")


@singledispatch
def decode_base64(b: str | bytes) -> str:
    """
    >>> decode_base64('ZGVmYXVsdDpkZWZhdWx0')
    'default:default'
    >>> decode_base64('ZXNwZW4')
    Traceback (most recent call last):
    ...
    binascii.Error: Incorrect padding
    >>> decode_base64('ZXNwZW4=')
    'espen'

    Raises:
        binascii.Error
    """
    raise NotImplementedError


@decode_base64.register
def decode_base64_bytes(b: bytes):
    return b64decode(b).decode("utf-8")


@decode_base64.register
def decode_base64_str(s: str) -> str:
    b = s.encode(encoding="utf-8")
    return b64decode(b).decode("utf-8")


def generate_secret_base_64(token_bytes_size: int = 16) -> str:
    """
    >>> len(generate_secret_base_64())
    24
    >>> len(generate_secret_base_64(token_bytes_size=24))
    32

    """

    return encode_base64(token_bytes(token_bytes_size))
