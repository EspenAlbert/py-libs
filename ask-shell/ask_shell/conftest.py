import pytest
from rich.console import Console
from zero_3rdparty.file_utils import ensure_parents_write_text

from ask_shell._run import stop_runs_and_pool
from ask_shell.interactive_rich import reset_progress
from ask_shell.settings import AskShellSettings


@pytest.fixture(autouse=True)
def settings(tmp_path, monkeypatch) -> AskShellSettings:
    static_dir = tmp_path / "static"
    cache_dir = tmp_path / "cache"
    static_dir.mkdir()
    cache_dir.mkdir()
    monkeypatch.setenv("STATIC_DIR", str(tmp_path))
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    return AskShellSettings.from_env()


tf_example = """\
terraform {
  required_providers {
    local = {
      source  = "hashicorp/local"
      version = "2.4.1"
    }
  }
}
"""


@pytest.fixture()
def tf_dir(settings):
    """Fixture to create a temporary directory with a Terraform example."""
    tf_path = settings.static_root / "terraform_example/main.tf"
    ensure_parents_write_text(tf_path, tf_example)
    return tf_path.parent


@pytest.fixture(scope="session", autouse=True)
def stop_consumer():
    yield
    stop_runs_and_pool()


@pytest.fixture(autouse=True)
def reset_progress_fix():
    reset_progress()


# https://github.com/Textualize/rich/blob/8c4d3d1d50047e3aaa4140d0ffc1e0c9f1df5af4/tests/test_live.py#L11
def create_capture_console(
    *, width: int = 60, height: int = 80, force_terminal: bool = True
) -> Console:
    return Console(
        width=width,
        height=height,
        force_terminal=force_terminal,
        legacy_windows=False,
        color_system=None,  # use no color system to reduce complexity of output,
        _environ={},
    )


@pytest.fixture()
def capture_console() -> Console:  # type: ignore
    """
    Fixture to capture output from the console.
    """
    console = create_capture_console()
    console.begin_capture()
    yield console  # type: ignore
    console.end_capture()
