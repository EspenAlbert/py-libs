import pytest
from model_lib import StaticSettings


@pytest.fixture
def static_env_vars(tmp_path, monkeypatch) -> StaticSettings:
    settings = StaticSettings.for_testing(tmp_path=tmp_path)
    monkeypatch.setenv("STATIC_DIR", str(settings.STATIC_DIR))
    monkeypatch.setenv("CACHE_DIR", str(settings.CACHE_DIR))
    return settings
