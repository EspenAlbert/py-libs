# otherwise pants will not include the file in the tests
# flake8: noqa
from model_lib.serialize.base_64 import decode_base64, encode_base64


def test_encode_str() -> None:
    s = "espen er kål"
    as_b64 = encode_base64(s)
    back_again = decode_base64(as_b64)
    assert s == back_again
