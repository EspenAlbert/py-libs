import pytest


@pytest.fixture(autouse=True)
def ensure_static_dir(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    cache_dir = tmp_path / "cache"
    static_dir.mkdir()
    cache_dir.mkdir()
    monkeypatch.setenv("STATIC_DIR", str(tmp_path))
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
