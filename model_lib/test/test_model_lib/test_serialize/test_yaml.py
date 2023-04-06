from pathlib import Path

# flake8: noqa
# otherwise pants will not include the file in the tests
from model_lib.serialize import *
from model_lib.serialize import yaml_serialize
from model_lib.serialize.yaml_serialize import (
    _add_brackets,
    _dedent_standalone_brackets,
    _indent_standalone_templates,
    _replace_brackets,
    dump_yaml_file,
    edit_yaml,
    multiline_pipe_style,
    parse_yaml_file,
)
from zero_lib.dict_nested import read_nested


def test_edit_index(tmp_path):
    data = dict(spec=dict(containers=[dict(name="cont1"), dict(name="cont2")]))
    path = tmp_path / "test_yaml_edit_index.yaml"
    dump_yaml_file(path, data)
    with edit_yaml(path, yaml_path="spec.containers.[1]") as cont2:
        assert cont2["name"] == "cont2"
        cont2["new"] = "YES"
    loaded = parse_yaml_file(path)
    assert loaded != data
    assert read_nested(loaded, "spec.containers.[1].new") == "YES"


DIR = Path(__file__).parent


def test_dumping_multiline_str(tmp_path, file_regression):
    """https://stackoverflow.com/questions/8640959/how-can-i-control-what-
    scalar-form-pyyaml-uses-for-my-data."""
    out_path = tmp_path / "with_multiline"
    with multiline_pipe_style():
        dump_yaml_file(
            out_path, dict(a="normal_single_line", b="Line1\nLine2\nLine3\n")
        )
    out_path_after = tmp_path / "without_multiline"
    dump_yaml_file(
        out_path_after, dict(a="normal_single_line", b="Line1\nLine2\nLine3\n")
    )
    content = "---\n".join(
        f"#{path.name}:\n{path.read_text()}" for path in [out_path, out_path_after]
    )
    file_regression.check(content, fullpath=DIR / "yaml_multiline.yaml")


def test_replace_brackets(file_regression, original_datadir):
    deployment_yaml = original_datadir / "deployment.yaml"
    remove_brackets = _replace_brackets(deployment_yaml.read_text())
    no_brackets = original_datadir / "no_brackets.yaml"
    file_regression.check(remove_brackets, fullpath=no_brackets)


def test_indent_standalone_templates(file_regression, original_datadir):
    no_brackets = original_datadir / "no_brackets.yaml"
    indented_standalone_templates = _indent_standalone_templates(
        no_brackets.read_text()
    )
    loadable_template = original_datadir / "loadable_template.yaml"
    file_regression.check(indented_standalone_templates, fullpath=loadable_template)


def test_dedent_standalone_brackets(file_regression, original_datadir):
    loadable_template = original_datadir / "loadable_template.yaml"
    dedent_no_brackets = _dedent_standalone_brackets(loadable_template.read_text())
    dedent_no_brackets_path = original_datadir / "dedent_no_brackets.yaml"
    file_regression.check(dedent_no_brackets, fullpath=dedent_no_brackets_path)


def test_add_brackets(file_regression, original_datadir):
    dedent_no_brackets_path = original_datadir / "dedent_no_brackets.yaml"
    template_extra_quotes = _add_brackets(dedent_no_brackets_path.read_text())
    template_extra_quotes_path = original_datadir / "template.yaml"
    file_regression.check(template_extra_quotes, fullpath=template_extra_quotes_path)
    deployment_yaml = original_datadir / "deployment.yaml"
    assert template_extra_quotes == deployment_yaml.read_text()
