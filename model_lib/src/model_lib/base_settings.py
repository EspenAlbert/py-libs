from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import Field
from pydantic.fields import FieldInfo

from zero_3rdparty.run_env import running_in_container_environment

logger = logging.getLogger(__name__)


def env_value_as_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (Path, bool, float, int)):
        value = str(value)
    if isinstance(value, (list, dict)):
        value = json.dumps(value)
    assert isinstance(value, str), f"env value must be str, was {value!r}"
    return value


T = TypeVar("T")


def container_or_default(container_default: T, cls_default: T) -> FieldInfo:
    return Field(
        default_factory=DockerOrClsDefDefault(
            docker_default=container_default, cls_default=cls_default
        )
    )


@dataclass
class DockerOrClsDefDefault(Generic[T]):
    docker_default: T
    cls_default: T

    def __call__(self) -> T:
        if running_in_container_environment():
            return self.docker_default
        return self.cls_default


def port_info(number: int, *, url_prefix: str, protocol: str) -> int:
    """Used for pants plugin "artifacts" to know which url_prefix and protocol
    to use in Chart."""
    return Field(default=number)
