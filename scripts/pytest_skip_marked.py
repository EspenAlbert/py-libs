import logging
import os

import pytest
from _pytest.python import CallSpec2

logger = logging.getLogger(__name__)


def _fixture_has_skip_marker(fixture_name: str, fixture_def) -> bool:
    markers = getattr(fixture_def.func, "pytestmark", [])
    return any(marker.name.startswith("skip") for marker in markers)


def pytest_collection_modifyitems(config, items):
    """Skip tests that are marked with @pytest.mark.skip
    To avoid the terminal session in VS Code that might have extra env-vars set accidentally run marked tests"""
    skip_marked_tests = os.getenv("SKIP_MARKED_TESTS", "false").lower() in (
        "true",
        "1",
        "yes",
    )
    if not skip_marked_tests:
        return
    for item in items:
        if any(marker.name.startswith("skip") for marker in item.own_markers):
            item.add_marker(
                pytest.mark.skip(
                    reason="Skipping test due to SKIP_MARKED_TESTS environment variable"
                )
            )
            continue
        item_session: pytest.Session = item.session
        fixture_manager = item_session._fixturemanager
        call_spec: CallSpec2 | None = getattr(item, "callspec", None)
        for fixture_name in item.fixturenames:
            if (
                fixture_name == "request"
                or call_spec
                and fixture_name in call_spec.params
            ):
                continue
            fixturedefs: list = fixture_manager.getfixturedefs(fixture_name, item)  # type: ignore
            if not fixturedefs:
                logger.warning(
                    f"No fixture definitions found for {fixture_name} in {item}"
                )
                continue
            assert len(fixturedefs) == 1, (
                f"Expected one fixture definition for {fixture_name}, got {len(fixturedefs)}"
            )
            if _fixture_has_skip_marker(fixture_name, fixturedefs[0]):
                item.add_marker(
                    pytest.mark.skip(
                        reason=f"Skipping test due to fixture {fixture_name} having skip marker"
                    )
                )
                break
