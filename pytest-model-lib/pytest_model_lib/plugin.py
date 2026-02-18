import os

import pytest
from model_lib import StaticSettings


def skip_unless_env(env_var: str) -> str:
    """Returns the env var value or skips the test/fixture."""
    value = os.environ.get(env_var, "")
    if not value:
        pytest.skip(f"needs os.environ[{env_var}]")
    return value


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "manual: test requires manual env setup (not run in CI)"
    )


@pytest.fixture
def static_env_vars(tmp_path, monkeypatch) -> StaticSettings:
    settings = StaticSettings.for_testing(tmp_path=tmp_path)
    monkeypatch.setenv("STATIC_DIR", str(settings.STATIC_DIR))
    monkeypatch.setenv("CACHE_DIR", str(settings.CACHE_DIR))
    return settings
