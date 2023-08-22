from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from contextlib import suppress
from typing import Any, Callable

from model_lib import ModelT
from model_lib.constants import (
    METADATA_DUMP_KEY,
    METADATA_MODEL_NAME_FIELD,
    MODEL_DUMP_KEY,
)
from model_lib.errors import FileFormat
from model_lib.metadata.metadata_dump import dump_metadata
from model_lib.model_dump import registered_types
from model_lib.pydantic_utils import model_json
from model_lib.serialize.json_serialize import dump as _dump_json
from model_lib.serialize.json_serialize import parse as _parse_json
from model_lib.serialize.json_serialize import pretty_dump as _dump_pretty_json
from model_lib.serialize.toml_serialize import add_line_breaks, dump_toml_str
from model_lib.serialize.yaml_serialize import dump_yaml_str

logger = logging.getLogger(__name__)


def dump_as_toml_str(instance: object, **kwargs) -> str:
    compact = dump_as_toml_str_compact(instance, **kwargs)
    return add_line_breaks(compact)


def dump_as_toml_str_compact(instance: object, **kwargs) -> str:
    # dumps to json and parse 1st to support custom types
    # and since an error will have a side effect on the instance creating a _TomlObject
    if isinstance(instance, list):
        raw: list = dump_as_list(instance)
    else:
        raw: dict = dump_as_dict(instance)  # type: ignore
    return dump_toml_str(raw, **kwargs)


_payload_dumpers: dict[FileFormat | str, Callable[[Any], str]] = {
    FileFormat.json: _dump_json,
    FileFormat.yaml: dump_yaml_str,
    FileFormat.yml: dump_yaml_str,
    FileFormat.pretty_json: _dump_pretty_json,
    FileFormat.json_pretty: _dump_pretty_json,
    FileFormat.json_pydantic: model_json,
    FileFormat.pydantic_json: model_json,
    FileFormat.toml: dump_as_toml_str,
    FileFormat.toml_compact: dump_as_toml_str_compact,
}


def dump(instance: object, format: FileFormat | str) -> str:
    """
    >>> dump('', "json")
    ''
    """
    if instance == "":
        #: special case where we would get '""' otherwise
        return ""
    dumper = _payload_dumpers[format]
    return dumper(instance)


def dump_as_dict(instance: object) -> dict:
    safe_instance_payload = _dump_json(instance)
    return _parse_json(safe_instance_payload)


def dump_as_list(instance: Iterable[ModelT]) -> list:
    safe_instance_payload = _dump_json(instance)
    return _parse_json(safe_instance_payload)


def dump_as_type_dict_list(instances: Iterable[ModelT], format: FileFormat) -> str:
    return dump([{type(instance).__name__: instance} for instance in instances], format)


def dump_as_type_dict(instances: Iterable[ModelT], format: FileFormat) -> str:
    return dump({type(instance).__name__: instance for instance in instances}, format)


def dump_safe(
    message: dict | object, format: FileFormat | str = FileFormat.json
) -> str:
    try:
        return dump(message, format)
    except TypeError as e:
        # Type is not JSON serializable: TestApp
        logger.warning(e)
        safe_types = set(registered_types())
        safe_types_tuple = tuple(safe_types)

        def is_safe(value: type):
            return value in safe_types or issubclass(value, safe_types_tuple)

        with suppress(Exception):
            message_safe = {
                key: value if is_safe(type(value)) else str(value)
                for key, value in message.items()  # type: ignore
            }
            return dump(message_safe, format=format)
        # noinspection PyUnreachableCode
        logger.critical(f"failed to dump {str(message)}")
    except Exception as e:
        logger.exception(e)
    return ""


def dump_with_metadata(
    model: object,
    metadata: Mapping[str, object] | None = None,
    format: FileFormat | str = FileFormat.json,
    override_model_name: str = "",
    *,
    skip_dumpers: bool = False,
    _model_field=MODEL_DUMP_KEY,
    _metadata_field=METADATA_DUMP_KEY,
) -> str:
    """
    Args:
        override_model_name: will add a
    """
    dumped_metadata = dump_metadata(skip_dumpers=skip_dumpers)
    model_name = override_model_name or type(model).__name__
    dumped_metadata[METADATA_MODEL_NAME_FIELD] = model_name
    if metadata:
        dumped_metadata.update(metadata)
    return dump({_model_field: model, _metadata_field: dumped_metadata}, format)
