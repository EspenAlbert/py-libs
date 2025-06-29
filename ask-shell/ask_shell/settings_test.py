import os

import pytest


@pytest.mark.skipif(os.environ.get("SLOW", "") == "", reason="needs os.environ[SLOW]")
def test_using_run_logs_dir_and_adding_1000_dirs_should_not_clean_it(
    tmp_path, settings
):
    run_logs_dir = settings.run_logs_dir = tmp_path / "run_logs"
    assert (
        settings.configure_run_logs_dir_if_unset(
            new_absolute_path=run_logs_dir, skip_env_update=True
        )
        == run_logs_dir
    )
    for i in range(100):
        run_dir = settings.next_run_logs_dir(f"test-{i}")
        if i == 0:
            assert run_dir.name == "001_test-0"
        elif i == 99:
            assert run_dir.name == "100_test-99"
        run_dir.mkdir(parents=True, exist_ok=True)
    assert len(list(run_logs_dir.iterdir())) == 100
    last_dir = settings.next_run_logs_dir("test-100")
    last_dir.mkdir(parents=True, exist_ok=True)
    assert last_dir.name == "101_test-100"
    assert len(list(run_logs_dir.iterdir())) == 101, (
        "Run logs directory should be cleaned up"
    )
    for i in range(1_000):
        run_dir = settings.next_run_logs_dir(f"test-{i}")
        run_dir.mkdir(parents=True, exist_ok=True)
        if i == 999:
            assert run_dir.name == "1101_test-999"


def test_configure_run_logs_dir_if_unset(tmp_path, settings):
    cache_root = settings.cache_root
    assert cache_root == tmp_path / "cache/ask_shell"
    new_run_logs_dir = settings.configure_run_logs_dir_if_unset(
        new_relative_path="my-app/test-command",
        skip_env_update=True,
        date_folder_expressing=None,
    )
    assert new_run_logs_dir == cache_root / "my-app/test-command"
    settings.run_logs_dir = None
    re_configured = settings.configure_run_logs_dir_if_unset(
        new_relative_path="my-app/test-command", skip_env_update=True
    )
    assert re_configured != new_run_logs_dir
    assert re_configured.name.endswith("Z")
