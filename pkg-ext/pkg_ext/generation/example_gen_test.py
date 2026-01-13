from pkg_ext.config import Stability
from pkg_ext.generation.example_gen import (
    generate_class_example_class,
    generate_function_example_class,
    generate_group_examples_file,
    slug,
)
from pkg_ext.models.api_dump import (
    CallableSignature,
    ClassDump,
    ClassFieldInfo,
    FuncParamInfo,
    FunctionDump,
    GroupDump,
    ParamKind,
)


def test_slug():
    assert slug("hello world") == "hello_world"
    assert slug("HelloWorld") == "helloworld"
    assert slug("parse_config") == "parse_config"
    assert slug("Some.Thing!") == "something"


def test_generate_function_example_class():
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
    result = generate_function_example_class(func)
    assert "class ParseConfigExample(Example[Any]):" in result
    assert "path: Path = ..." in result
    assert "timeout: int | None = ..." in result


def test_generate_function_skips_special_params():
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
    result = generate_function_example_class(func)
    assert "self" not in result
    assert "args" not in result
    assert "kwargs" not in result
    assert "data: str = ..." in result


def test_generate_class_example_class():
    cls = ClassDump(
        name="UserConfig",
        module_path="config",
        fields=[
            ClassFieldInfo(name="name", type_annotation="str"),
            ClassFieldInfo(name="age", type_annotation="int | None"),
            ClassFieldInfo(name="CLASS_VAR", is_class_var=True),
            ClassFieldInfo(name="computed", is_computed=True),
        ],
    )
    result = generate_class_example_class(cls)
    assert "class UserConfigExample(Example[UserConfig]):" in result
    assert "name: str = ..." in result
    assert "age: int | None = ..." in result
    assert "CLASS_VAR" not in result
    assert "computed" not in result


def test_generate_group_examples_file():
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
        ],
    )
    result = generate_group_examples_file(group, "my_pkg")
    assert "class Example(BaseModel, Generic[T]):" in result
    assert "example_name: str" in result
    assert "expected: Callable" in result
    assert "class LoadExample(Example[Any]):" in result
    assert "DO_NOT_EDIT: pkg-ext header" in result
    assert "OK_EDIT: pkg-ext header" in result
    assert "DO_NOT_EDIT: pkg-ext class_load" in result
    assert "OK_EDIT: pkg-ext class_load" in result


def test_generate_group_examples_file_with_imports():
    """Ensure type imports are generated from type_imports field."""
    group = GroupDump(
        name="sections",
        stability=Stability.ga,
        symbols=[
            ClassDump(
                name="CommentConfig",
                module_path="my_pkg.sections",
                fields=[
                    ClassFieldInfo(name="prefix", type_annotation="str"),
                ],
            ),
            FunctionDump(
                name="parse_sections",
                module_path="my_pkg.sections",
                signature=CallableSignature(
                    parameters=[
                        FuncParamInfo(
                            name="path",
                            kind=ParamKind.POSITIONAL_OR_KEYWORD,
                            type_annotation="Path",
                            type_imports=["pathlib.Path"],
                        ),
                        FuncParamInfo(
                            name="config",
                            kind=ParamKind.POSITIONAL_OR_KEYWORD,
                            type_annotation="CommentConfig",
                            type_imports=["my_pkg.sections.CommentConfig"],
                        ),
                    ]
                ),
            ),
        ],
    )
    result = generate_group_examples_file(group, "my_pkg")
    assert "from pathlib import Path" in result
    assert "from my_pkg.sections import CommentConfig" in result
