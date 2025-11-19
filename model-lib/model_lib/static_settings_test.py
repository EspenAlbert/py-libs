import os

import pytest

from model_lib import StaticSettings


@pytest.fixture
@pytest.mark.skipif(
    os.environ.get("EXTERNAL_API_KEY", "") == "",
    reason="needs os.environ[EXTERNAL_API_KEY]",
)
def external_api_key():
    """Fixture that requires EXTERNAL_API_KEY to be set"""
    return os.environ.get("EXTERNAL_API_KEY")


def test_static_settings_for_testing(tmp_path):
    settings = StaticSettings.for_testing(tmp_path=tmp_path)
    assert settings.STATIC_DIR == tmp_path / "static"
    assert settings.CACHE_DIR == tmp_path / "cache"
    assert settings.STATIC_DIR.exists()
    assert settings.CACHE_DIR.exists()


def test_static_settings_app_name():
    assert StaticSettings.app_name() == "static"


def test_static_settings_roots(tmp_path):
    settings = StaticSettings.for_testing(tmp_path=tmp_path)
    assert settings.static_root == settings.STATIC_DIR / "static"
    assert settings.cache_root == settings.CACHE_DIR / "static"


def test_static_settings_skip_app_name(tmp_path):
    settings = StaticSettings.for_testing(tmp_path=tmp_path, SKIP_APP_NAME=True)
    assert settings.static_root == settings.STATIC_DIR
    assert settings.cache_root == settings.CACHE_DIR


@pytest.mark.skipif(
    os.environ.get("JIRA_TOKEN", "") == "",
    reason="needs os.environ[JIRA_TOKEN]",
)
def test_with_jira_token_required():
    """This test requires JIRA_TOKEN to be set in environment.
    It will be skipped when SKIP_MARKED_TESTS=true is set."""
    jira_token = os.environ.get("JIRA_TOKEN")
    assert jira_token
    assert len(jira_token) > 0


@pytest.mark.skip(reason="Example test that should be skipped with SKIP_MARKED_TESTS")
def test_always_skip_when_skip_marked_tests():
    """This test should be skipped when SKIP_MARKED_TESTS=true"""
    msg = "This should never run when SKIP_MARKED_TESTS is enabled"
    raise AssertionError(msg)


def test_with_external_api_fixture(external_api_key):
    """This test uses a fixture with skip marker.
    It should be skipped when SKIP_MARKED_TESTS=true and EXTERNAL_API_KEY is not set."""
    assert external_api_key
    assert len(external_api_key) > 0
