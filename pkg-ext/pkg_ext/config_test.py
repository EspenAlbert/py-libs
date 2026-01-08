from pkg_ext.config import GroupConfig, Stability, load_project_config

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
flat_package = true

[tool.pkg-ext.groups.datez]
stability = "ga"
docstring = "Date utilities"

[tool.pkg-ext.groups.filez]
dependencies = ["datez"]
stability = "beta"
docs_exclude = ["_internal_helper"]
"""


def test_load_project_config_with_groups(tmp_path):
    file = tmp_path / "pyproject.toml"
    file.write_text(pyproject_with_groups)
    config = load_project_config(tmp_path)

    assert config.flat_package
    assert len(config.groups) == 2

    datez = config.groups["datez"]
    assert datez.stability == Stability.ga
    assert datez.docstring == "Date utilities"
    assert datez.dependencies == []

    filez = config.groups["filez"]
    assert filez.stability == Stability.beta
    assert filez.dependencies == ["datez"]
    assert filez.docs_exclude == ["_internal_helper"]


def test_group_config_defaults():
    cfg = GroupConfig()
    assert cfg.dependencies == []
    assert cfg.stability == Stability.ga
    assert cfg.docs_exclude == []
    assert cfg.docstring == ""
