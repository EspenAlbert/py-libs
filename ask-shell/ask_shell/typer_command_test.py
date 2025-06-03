import logging

from ask_shell.typer_command import hide_secrets


def test_hide_secrets(caplog, tmp_path):
    root_logger = logging.getLogger()
    handler = root_logger.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    secrets = {
        "SECRET_KEY": "my_secret_value",
        "ANOTHER_KEY": "another",
        "token": "adsfadf",
        "ok": "some-value",
        "my-secret-path": str(tmp_path),
    }
    hide_secrets(handler, secrets)
    expect_hidden = {
        value for key, value in secrets.items() if key not in {"ok", "my-secret-path"}
    }
    expect_shown = {
        value for key, value in secrets.items() if key in {"ok", "my-secret-path"}
    }
    all_vars_logged = ",".join(f"{key}={value}" for key, value in secrets.items())
    root_logger.warning(f"Logging all variables: {all_vars_logged}")
    output = caplog.text
    found_hidden = {value for value in expect_hidden if value in output}
    assert not found_hidden
    found_shown: set[str] = {value for value in expect_shown if value in output}
    assert found_shown == expect_shown, (
        f"Expected to find {expect_shown}, but found {found_shown}"
    )
