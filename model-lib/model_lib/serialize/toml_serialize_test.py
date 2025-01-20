from model_lib import Event, FileFormat, dump, parse_model, parse_payload
from model_lib.serialize.toml_serialize import add_line_breaks

_toml_example = """\
[GLOBAL]
pants_version = "2.17.0rc3"
print_stacktrace = true
level = "warn"
build_file_prelude_globs = ["_pants/*.py"]

# for plugin development
pythonpath = ["%(buildroot)s/_pants/pants_py_deploy/src", "%(buildroot)s/compose_chart_export/src", "%(buildroot)s/docker_compose_parser/src", "%(buildroot)s/model_lib/src", "%(buildroot)s/zero_3rdparty/src"]
plugins = [
  "pydevd-pycharm==231.8109.197",
  "PyYAML==6.0.1",
  "pydantic==1.10.2",
  "orjson==3.6.5",
  "semver==2.13.0"
]
[anonymous-telemetry]
enabled="false"

[source]
root_patterns = ["/*/src", "/*/", "/*/tests", "/*/test", "/_pants/*/src", "/_pants/*/tests", "/_pants/3rdparty"]

[python]
interpreter_constraints=[">=3.9"]
enable_resolves = true

[python-infer]
use_rust_parser = true

[python.resolves]
pants-plugins = "_pants/3rdparty/lock.txt"
pydantic-v1 = "3rdparty/python/pydantic-v1.lock"
python-default = "3rdparty/python/default.lock"

[python.resolves_to_interpreter_constraints]
pants-plugins = [">=3.9,<3.10"]
python-default = [">=3.9"]
pydantic-v1 = [">=3.9"]

[black]
config = "pyproject.toml"

[mypy]
config = "pyproject.toml"
install_from_resolve="python-default"
interpreter_constraints=[">=3.11"]
"""


def test_parse_toml_str():
    parsed = parse_payload(_toml_example, "toml")
    assert isinstance(parsed, dict)
    assert parsed["black"] == {"config": "pyproject.toml"}


def test_parse_toml_path(tmp_path):
    path = tmp_path / "my_file.toml"
    path.write_text(_toml_example)
    parsed = parse_payload(path)
    assert isinstance(parsed, dict)
    assert parsed["black"] == {"config": "pyproject.toml"}


class _TomlChild(Event):
    age: int


class _TomlModel(Event):
    name: str
    child: _TomlChild


_SOME_TOML = 'name = "I am toml!"\n\n[child]\nage = 2'

model_example = _TomlModel(name="I am toml!", child=_TomlChild(age=2))


def test_dump_toml():
    instance = model_example
    dumped = dump(instance, "toml")
    assert dumped == f"{_SOME_TOML}"


def test_parse_model():
    assert parse_model(_SOME_TOML, t=_TomlModel, format="toml") == model_example


_example = """\
[GLOBAL]
backend_packages = ["pants.backend.awslambda.python", "pants.backend.build_files.fmt.black", "pants.backend.codegen.protobuf.python", "pants.backend.docker", "pants.backend.experimental.helm", "pants.backend.experimental.python", "pants.backend.experimental.python.lint.ruff", "pants.backend.python", "pants.backend.python.lint.black", "pants.backend.python.mixed_interpreter_constraints", "pants.backend.python.typecheck.mypy"]
build_file_prelude_globs = ["_pants/*.py"]
"""
_example_with_linebreaks = """\
[GLOBAL]
backend_packages = [
  "pants.backend.awslambda.python",
  "pants.backend.build_files.fmt.black",
  "pants.backend.codegen.protobuf.python",
  "pants.backend.docker",
  "pants.backend.experimental.helm",
  "pants.backend.experimental.python",
  "pants.backend.experimental.python.lint.ruff",
  "pants.backend.python",
  "pants.backend.python.lint.black",
  "pants.backend.python.mixed_interpreter_constraints",
  "pants.backend.python.typecheck.mypy",
]
build_file_prelude_globs = ["_pants/*.py"]"""


def test_add_line_breaks():
    assert add_line_breaks(_example) == _example_with_linebreaks


def test_toml_compact(file_regression):
    payload = parse_payload(_example, FileFormat.toml_compact)
    file_regression.check(dump(payload, FileFormat.toml_compact), extension=".toml")


def test_toml_normal(file_regression):
    payload = parse_payload(_example, FileFormat.toml_compact)
    file_regression.check(dump(payload, FileFormat.toml), extension=".toml")
