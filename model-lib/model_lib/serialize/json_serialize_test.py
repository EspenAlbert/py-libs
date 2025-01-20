import pytest

from model_lib.serialize.json_serialize import (
    dump,
    parse,
    pretty_dump,
    stdlib_dumps_parse,
)

stdlib_dump, stdlib_dump_pretty, stdlib_parse = stdlib_dumps_parse()


@pytest.mark.parametrize(
    "dumper_func", [dump, pretty_dump, stdlib_dump, stdlib_dump_pretty]
)
def test_dump(dumper_func):
    d = dict(a=1, b={1: "value"})
    dumped = dumper_func(d)
    if dumper_func in [pretty_dump, stdlib_dump_pretty]:
        assert dumped == '{\n  "a": 1,\n  "b": {\n    "1": "value"\n  }\n}'
    else:
        assert dumped == '{"a":1,"b":{"1":"value"}}'
    # notice how the key b.1 is now a string
    expected_parsed = dict(a=1, b={"1": "value"})
    assert parse(dumped) == expected_parsed
    assert stdlib_parse(dumped) == expected_parsed
