from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import pytest
import yaml

from model_lib import Entity, Event, register_dumper
from model_lib.serialize import dump
from model_lib.serialize.yaml_serialize import (
    no_timestamp_conversion,
    no_yaml_anchors,
)


@dataclass
class _MyClass:
    name: str
    age: int


register_dumper(_MyClass, asdict, allow_override=True)


class _MyEntity(Entity):
    name: str
    age: int


class _MyEvent(Event):
    name: str
    age: int


@pytest.mark.parametrize("cls", [_MyClass, _MyEntity, _MyEvent])
def test_safe_dump(cls):
    dumped = dump(cls(name="espen", age=99), "yaml")
    assert dumped == "name: espen\nage: 99\n"


def test_no_yaml_anchors():
    """Test that no_yaml_anchors context manager prevents YAML anchor/alias references."""
    timestamp = datetime.now(UTC)
    # Create data with duplicate datetime objects that would normally create anchors
    data = {
        "task1": {"ts": timestamp, "name": "Task 1"},
        "task2": {"ts": timestamp, "name": "Task 2"},  # Same timestamp object
    }

    # Without context manager, YAML may create anchors for duplicate objects
    dumped_without_context = dump(data, "yaml")
    # With context manager, anchors should be prevented
    with no_yaml_anchors():
        dumped_with_context = dump(data, "yaml")

    # Check if anchors were created without context manager
    has_anchors_without = (
        "*id" in dumped_without_context or "&id" in dumped_without_context
    )
    assert has_anchors_without

    # Verify that WITH context manager, no anchors are present
    assert "*id" not in dumped_with_context
    assert "&id" not in dumped_with_context
    # Verify timestamps are serialized as actual values in both cases
    assert "ts:" in dumped_without_context
    assert "ts:" in dumped_with_context


def test_no_timestamp_conversion():
    """Test that no_timestamp_conversion prevents PyYAML from auto-converting datetime strings."""
    yaml_content = "ts: 2025-11-26 06:50:26.980008+00:00\nname: Test Task\n"

    # Without context manager, PyYAML auto-converts to datetime object
    without_context: dict = yaml.safe_load(yaml_content)  # type: ignore[assignment]
    assert isinstance(without_context["ts"], datetime)
    # Verify the timestamp was converted (check it's a datetime, not a string)
    assert without_context["ts"] == datetime(2025, 11, 26, 6, 50, 26, 980008, UTC)

    # With context manager, datetime string remains as string
    with no_timestamp_conversion():
        with_context: dict = yaml.safe_load(yaml_content)  # type: ignore[assignment]
    assert isinstance(with_context["ts"], str)
    assert with_context["ts"] == "2025-11-26 06:50:26.980008+00:00"
