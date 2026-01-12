from pkg_ext.config import Stability
from pkg_ext.generation import test_gen
from pkg_ext.models.api_dump import (
    CallableSignature,
    ClassDump,
    ClassFieldInfo,
    FuncParamInfo,
    FunctionDump,
    GroupDump,
    ParamKind,
)


def test_generate_func_test():
    func = FunctionDump(
        name="parse_config",
        module_path="config",
        signature=CallableSignature(
            parameters=[
                FuncParamInfo(
                    name="path",
                    kind=ParamKind.POSITIONAL_OR_KEYWORD,
                    type_annotation="Path",
                ),
                FuncParamInfo(
                    name="timeout",
                    kind=ParamKind.KEYWORD_ONLY,
                    type_annotation="int | None",
                ),
            ]
        ),
    )
    result = test_gen._generate_func_test(func, "config")
    assert "parse_config_examples = [e for e in vars(examples_module)" in result
    assert "isinstance(e, examples_module.ParseConfigExample)" in result
    assert '@pytest.mark.parametrize("example", parse_config_examples' in result
    assert "ids=[e.example_name for e in parse_config_examples]" in result
    assert (
        "def test_parse_config(example: examples_module.ParseConfigExample):" in result
    )
    assert "result = parse_config(path=example.path, timeout=example.timeout)" in result


def test_generate_func_test_skips_special_params():
    func = FunctionDump(
        name="my_func",
        module_path="mod",
        signature=CallableSignature(
            parameters=[
                FuncParamInfo(name="self", kind=ParamKind.POSITIONAL_OR_KEYWORD),
                FuncParamInfo(name="args", kind=ParamKind.VAR_POSITIONAL),
                FuncParamInfo(
                    name="data",
                    kind=ParamKind.POSITIONAL_OR_KEYWORD,
                    type_annotation="str",
                ),
                FuncParamInfo(name="kwargs", kind=ParamKind.VAR_KEYWORD),
            ]
        ),
    )
    result = test_gen._generate_func_test(func, "mod")
    assert "self=example.self" not in result
    assert "args=example.args" not in result
    assert "kwargs=example.kwargs" not in result
    assert "data=example.data" in result


def test_generate_class_test():
    cls = ClassDump(
        name="UserConfig",
        module_path="config",
        fields=[
            ClassFieldInfo(name="name", type_annotation="str"),
        ],
    )
    result = test_gen._generate_class_test(cls, "config")
    assert "userconfig_examples = [e for e in vars(examples_module)" in result
    assert "isinstance(e, examples_module.UserConfigExample)" in result
    assert '@pytest.mark.parametrize("example", userconfig_examples' in result
    assert "def test_userconfig(example: examples_module.UserConfigExample):" in result
    assert (
        'UserConfig(**example.model_dump(exclude={"example_name", "example_description_md"}))'
        in result
    )


def test_generate_group_test_file():
    group = GroupDump(
        name="config",
        stability=Stability.ga,
        symbols=[
            FunctionDump(
                name="load",
                module_path="config.loader",
                signature=CallableSignature(
                    parameters=[
                        FuncParamInfo(
                            name="path",
                            kind=ParamKind.POSITIONAL_OR_KEYWORD,
                            type_annotation="str",
                        )
                    ]
                ),
            ),
            ClassDump(
                name="Settings",
                module_path="config.models",
                fields=[ClassFieldInfo(name="debug", type_annotation="bool")],
            ),
        ],
    )
    result = test_gen.generate_group_test_file(group, "my_pkg")
    assert "import pytest" in result
    assert "from my_pkg import config_examples as examples_module" in result
    assert "from my_pkg.config import load, Settings" in result
    assert "DO_NOT_EDIT: pkg-ext header" in result
    assert "OK_EDIT: pkg-ext header" in result
    assert "DO_NOT_EDIT: pkg-ext load_test_parametrize" in result
    assert "OK_EDIT: pkg-ext load_test_parametrize" in result
    assert "DO_NOT_EDIT: pkg-ext settings_test_parametrize" in result
    assert "OK_EDIT: pkg-ext settings_test_parametrize" in result


def test_generate_group_test_file_empty_group():
    group = GroupDump(name="empty", stability=Stability.ga, symbols=[])
    result = test_gen.generate_group_test_file(group, "my_pkg")
    assert "import pytest" in result
    assert "from my_pkg import empty_examples as examples_module" in result
    assert "DO_NOT_EDIT: pkg-ext header" in result
