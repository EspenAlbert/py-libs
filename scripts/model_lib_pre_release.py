import model_lib

yaml_snippet = """
name: hello
age: 1337
"""


class MyEntity(model_lib.Entity):
    name: str
    age: int


def model_lib_basic():
    parsed = model_lib.parse_payload(yaml_snippet, "yaml")
    assert parsed == {"name": "hello", "age": 1337}
    assert yaml_snippet.strip() == model_lib.dump(parsed, "yaml").strip()
    parsed_model = model_lib.parse_model(yaml_snippet, t=MyEntity, format="yaml")
    assert parsed_model == MyEntity(name="hello", age=1337)
    for dump_fmt in ["json", "yml", "toml"]:
        assert model_lib.dump(parsed_model, dump_fmt)
    print("check_yaml_basic passed ✅")  # noqa: T201


if __name__ == "__main__":
    model_lib_basic()
