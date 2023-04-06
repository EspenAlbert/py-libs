from contextlib import suppress
from copy import deepcopy
from typing import Any, Iterable, Mapping, TypeVar

from model_lib.metadata.context_dict import (
    CopyConfig,
    LocalDict,
    get_context_dict,
    set_copy_behavior,
)

_METADATA_LOCAL_KEY = __name__
T = TypeVar("T")


set_copy_behavior(
    _METADATA_LOCAL_KEY,
    CopyConfig(
        thread_copy=True,
        task_copy=True,
        copy_func=deepcopy,
    ),
)


def update_metadata(metadata: Mapping[str, Any] | Iterable[tuple[str, Any]]) -> dict:
    metadata_in_context = current_metadata()
    metadata_in_context.update(metadata)
    return metadata_in_context


def current_metadata() -> dict[str, Any]:
    context_dict = get_context_dict()
    return metadata_from_context_dict(context_dict)


def metadata_from_context_dict(context_dict: LocalDict) -> dict:
    return context_dict.setdefault(_METADATA_LOCAL_KEY, {})


def read_metadata(key: str) -> Any:
    """Raises KeyError."""
    return current_metadata()[key]


def read_metadata_or_none(key: str) -> Any:
    with suppress(KeyError):
        return read_metadata(key)


def set_metadata(key: str, value: Any) -> None:
    metadata = current_metadata()
    metadata[key] = value


def pop_metadata(key: str, default: T = None) -> T | None:
    metadata = current_metadata()
    return metadata.pop(key, default)
