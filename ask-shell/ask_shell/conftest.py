import pytest
from zero_3rdparty.file_utils import ensure_parents_write_text

from ask_shell._run import stop_runs_and_pool
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
