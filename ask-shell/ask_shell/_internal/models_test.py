import pytest
from pydantic import ValidationError

from ask_shell._internal._run import run_and_wait
from ask_shell._internal.models import (
    ERROR_MESSAGE_INTERACTIVE_SHELL,
    EmptyOutputError,
    ShellConfig,
)


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


def test_assertion_error_with_user_input():
    with pytest.raises(
        ValidationError,
        match=ERROR_MESSAGE_INTERACTIVE_SHELL,
    ):
        ShellConfig(
            shell_input="echo 'Hello'",
            user_input=True,
        )


def test_parse_output_dict(tmp_path):
    run = run_and_wait(
        ShellConfig(shell_input="""echo '{"field": "value"}'""", cwd=tmp_path)
    )
    assert run.parse_output(dict) == {"field": "value"}


def test_parse_output_list(tmp_path):
    run = run_and_wait(
        ShellConfig(shell_input="""echo '["value1", "value2"]'""", cwd=tmp_path)
    )
    assert run.parse_output(list) == ["value1", "value2"]


def test_parse_output_raise_output_error_on_empty(tmp_path):
    with pytest.raises(EmptyOutputError, match="No output in stdout for"):
        run_and_wait(ShellConfig(shell_input="echo ''", cwd=tmp_path)).parse_output(
            dict
        )
