import pytest

from pkg_ext.config import (
    GroupConfig,
    ProjectConfig,
    load_project_config,
    validate_group_dependencies,
)
from pkg_ext.models import PublicGroup, PublicGroups

example_pyproject_toml = """\
[tool.pkg-ext]
tag_prefix = "a"
after_file_write_hooks = [
  "just quick",
]
"""


def test_load_project_config(tmp_path):
    file = tmp_path / "pyproject.toml"
    file.write_text(example_pyproject_toml)
    config = load_project_config(tmp_path)
    assert config.after_file_write_hooks


pyproject_with_groups = """\
[tool.pkg-ext]

[tool.pkg-ext.groups.datez]
docstring = "Date utilities"

[tool.pkg-ext.groups.filez]
dependencies = ["datez"]
docs_exclude = ["_internal_helper"]
"""


def test_load_project_config_with_groups(tmp_path):
    file = tmp_path / "pyproject.toml"
    file.write_text(pyproject_with_groups)
    config = load_project_config(tmp_path)

    assert len(config.groups) == 2

    datez = config.groups["datez"]
    assert datez.docstring == "Date utilities"
    assert datez.dependencies == []

    filez = config.groups["filez"]
    assert filez.dependencies == ["datez"]
    assert filez.docs_exclude == ["_internal_helper"]


def test_group_config_defaults():
    cfg = GroupConfig()
    assert cfg.dependencies == []
    assert cfg.docs_exclude == []
    assert cfg.docstring == ""
    assert cfg.examples_enabled is None
    assert cfg.examples_include == []
    assert cfg.examples_exclude == []


def test_examples_include_exclude_mutually_exclusive():
    with pytest.raises(ValueError, match="mutually exclusive"):
        GroupConfig(examples_include=["a"], examples_exclude=["b"])


def test_filter_example_symbols():
    config = ProjectConfig(
        examples_enabled=True,
        groups={
            "disabled": GroupConfig(examples_enabled=False),
            "include_only": GroupConfig(examples_include=["func_a", "func_b"]),
            "exclude_some": GroupConfig(examples_exclude=["func_c"]),
        },
    )
    symbols = ["func_a", "func_b", "func_c"]
    assert config.filter_example_symbols("disabled", symbols) == []
    assert config.filter_example_symbols("include_only", symbols) == [
        "func_a",
        "func_b",
    ]
    assert config.filter_example_symbols("exclude_some", symbols) == [
        "func_a",
        "func_b",
    ]
    assert config.filter_example_symbols("unknown_group", symbols) == symbols


def test_filter_example_symbols_inherits_project_default():
    config = ProjectConfig(examples_enabled=False)
    assert config.filter_example_symbols("any_group", ["a", "b"]) == []

    config_enabled = ProjectConfig(
        examples_enabled=False, groups={"enabled": GroupConfig(examples_enabled=True)}
    )
    assert config_enabled.filter_example_symbols("enabled", ["a"]) == ["a"]


def test_filter_example_symbols_unknown_raises():
    config = ProjectConfig(
        examples_enabled=True,
        groups={"g": GroupConfig(examples_include=["unknown_func"])},
    )
    with pytest.raises(ValueError, match="unknown symbols.*unknown_func"):
        config.filter_example_symbols("g", ["real_func"])

    config_exclude = ProjectConfig(
        examples_enabled=True,
        groups={"g": GroupConfig(examples_exclude=["typo_func"])},
    )
    with pytest.raises(ValueError, match="unknown symbols.*typo_func"):
        config_exclude.filter_example_symbols("g", ["real_func"])


pyproject_valid_deps = """\
[tool.pkg-ext]
[tool.pkg-ext.groups.core]
[tool.pkg-ext.groups.utils]
dependencies = ["core", "__ROOT__"]
"""


def test_valid_dependencies(tmp_path):
    (tmp_path / "pyproject.toml").write_text(pyproject_valid_deps)
    config = load_project_config(tmp_path)
    assert config.groups["utils"].dependencies == ["core", "__ROOT__"]


pyproject_invalid_dep = """\
[tool.pkg-ext]
[tool.pkg-ext.groups.utils]
dependencies = ["nonexistent"]
"""


def test_invalid_dependency_raises(tmp_path):
    (tmp_path / "pyproject.toml").write_text(pyproject_invalid_dep)
    with pytest.raises(ValueError, match="invalid dependency 'nonexistent'"):
        load_project_config(tmp_path)


pyproject_circular = """\
[tool.pkg-ext]
[tool.pkg-ext.groups.a]
dependencies = ["b"]
[tool.pkg-ext.groups.b]
dependencies = ["a"]
"""


def test_circular_dependency_raises(tmp_path):
    (tmp_path / "pyproject.toml").write_text(pyproject_circular)
    with pytest.raises(ValueError, match="Circular dependency"):
        load_project_config(tmp_path)


def test_validate_group_dependencies_against_runtime():
    # Config deps are valid (core exists in config), but runtime is missing 'core'
    config = ProjectConfig(
        groups={"core": GroupConfig(), "utils": GroupConfig(dependencies=["core"])}
    )
    runtime = PublicGroups(groups=[PublicGroup(name="__ROOT__")])  # missing 'core'
    with pytest.raises(ValueError, match="unknown runtime group 'core'"):
        validate_group_dependencies(config, runtime)


def test_merge_config_and_write(tmp_path):
    config = ProjectConfig(
        groups={
            "datez": GroupConfig(docstring="Date utils"),
            "filez": GroupConfig(dependencies=["datez"]),
        }
    )
    output_path = tmp_path / ".groups.yaml"
    groups = PublicGroups(storage_path=output_path)
    groups.add_module("datez", "datez_module")
    groups.merge_config(config)
    groups.write()

    datez = groups.name_to_group["datez"]
    assert datez.docstring == "Date utils"
    assert "datez_module" in datez.owned_modules

    filez = groups.name_to_group["filez"]
    assert filez.dependencies == ["datez"]

    content = output_path.read_text()
    assert "docstring: Date utils" in content
    assert "dependencies:" in content
    assert "# generated by pkg-ext from pyproject.toml" in content
