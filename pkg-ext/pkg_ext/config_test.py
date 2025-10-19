from pkg_ext.config import load_project_config

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
