import pytest

from ask_shell import ShellConfig


def test_infer_print_prefix(tmp_path):
    cwd = tmp_path / "some-repo/tf_module"
    cwd.mkdir(parents=True)
    config = ShellConfig(shell_input="terraform apply", cwd=cwd)
    assert config.print_prefix == "some-repo/tf_module terraform apply"
    assert config.is_binary_call
    assert config.ansi_content
    assert config.env != {}


@pytest.mark.parametrize("flag", ["-chdir=DIR", "--chdir DIR", "-C DIR --other flag"])
def test_infer_print_prefix_with_global_flag(tmp_path, flag):
    cwd = tmp_path / "some-repo/tf_module"
    cwd.mkdir(parents=True)
    config = ShellConfig(
        shell_input=f"terraform {flag} apply", cwd=cwd, skip_os_env=True
    )
    assert config.print_prefix == "some-repo/tf_module terraform apply"
    assert config.env == {}
