# flake8: noqa
from __future__ import annotations

import logging
from contextlib import suppress
from functools import singledispatch
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Tuple, Type, TypeVar

from model_lib.constants import (
    FileFormat,
    ModelRawT,
    PayloadParser,
    PayloadT,
    RegisteredPayloadT,
)
from model_lib.errors import (
    PayloadError,
    PayloadParserAlreadyExistError,
    PayloadParserNotFoundError,
    UnknownModelError,
)
from model_lib.model_base import model_name_to_t
from zero_lib.file_utils import PathLike
from zero_lib.object_name import as_name

from .json_serialize import parse as parse_json
from .yaml_serialize import parse_yaml_str

logger = logging.getLogger(__name__)
_registered_parsers: Dict[Type[RegisteredPayloadT, PayloadParser]] = {}
T = TypeVar("T")


_format_parsers: Dict[FileFormat, Callable[[str], ModelRawT]] = {
    FileFormat.json: parse_json,
    FileFormat.yaml: parse_yaml_str,
}
_file_format_to_raw_format: Dict[str, FileFormat] = {
    ".json": FileFormat.json,
    ".yaml": FileFormat.yaml,
    ".yml": FileFormat.yaml,
}


def as_file_format(path: PathLike) -> FileFormat:
    path = Path(path)
    if file_format := _file_format_to_raw_format[path.suffix]:
        return file_format
    raise NotImplementedError


def parse_model(
    payload: PayloadT,
    t: Optional[Type[T]] = None,
    format: FileFormat = FileFormat.json,
    extra_kwargs: Mapping[str, Any] | None = None,
) -> T:
    model, _ = parse_model_metadata(
        payload, t=t, format=format, extra_kwargs=extra_kwargs
    )
    return model


def create_model(
    cls: Type[T], model_args: dict | Any, extra_kwargs: Mapping[str, Any]
) -> T:
    """Raises ValidationError."""
    model_kwargs = isinstance(model_args, dict)
    if extra_kwargs:
        return (
            cls(**(model_args | extra_kwargs))
            if model_kwargs
            else cls(model_args, **extra_kwargs)
        )
    return cls(**model_args) if model_kwargs else cls(model_args)


def _lookup_safe(model_name: str) -> Type[T] | None:
    with suppress(UnknownModelError):
        return model_name_to_t(model_name)


def parse_model_metadata(
    payload: PayloadT,
    format: FileFormat = FileFormat.json,
    t: Type[T] | None = None,
    extra_kwargs: Mapping[str, Any] | None = None,
) -> Tuple[T, dict[str, Any]]:
    """raises PayloadError or ValidationError."""
    try:
        parsed_payload = parse_payload(payload, format)
    except Exception as e:
        raise PayloadError(payload, message=f"parse error: {e!r}") from e
    # from constants
    # MODEL_DUMP_KEY = "model"
    # METADATA_DUMP_KEY = "metadata"
    # METADATA_MODEL_NAME_FIELD = "model_name"
    # METADATA_MODEL_NAME_BACKUP_FIELD = "model_name_backup"

    match parsed_payload:
        case {"metadata": metadata, "model": model_args}:
            if t:
                return create_model(t, model_args, extra_kwargs), metadata
            match metadata:
                case {"model_name": model_name, "model_name_backup": model_name_backup}:
                    model_cls = _lookup_safe(model_name) or _lookup_safe(
                        model_name_backup
                    )
                    if model_cls is None:
                        message = f"unknown models: {model_name}, {model_name_backup}"
                        raise PayloadError(parsed_payload, message, metadata)
                    return create_model(model_cls, model_args, extra_kwargs), metadata
                case {"model_name": model_name}:
                    model_cls = _lookup_safe(model_name)
                    if model_cls is None:
                        raise PayloadError(
                            parsed_payload, f"unknown model: {model_name}", metadata
                        )
                    return create_model(model_cls, model_args, extra_kwargs), metadata
                case _:
                    raise PayloadError(
                        payload=parsed_payload,
                        message="cannot infer model_cls",
                        metadata=metadata,
                    )
        case _ if t:
            return create_model(t, parsed_payload, extra_kwargs), {}
        case _:
            raise PayloadError(payload=payload, message="not a dictionary")


def parse_model_name_kwargs_list(payload: RegisteredPayloadT) -> list[T]:
    raw_events: list = parse_payload(payload)
    parsed_events = []
    for cls_name_kwargs in raw_events:
        cls_name, kwargs = cls_name_kwargs.popitem()
        cls = model_name_to_t(cls_name)
        parsed_events.append(cls(**kwargs))
    return parsed_events


@singledispatch
def parse_payload(payload: object, format=FileFormat.json) -> ModelRawT:
    raise PayloadParserNotFoundError(payload=payload, format=format)


@parse_payload.register
def _parse_str(payload: str, format=FileFormat.json):
    parser = _format_parsers[format]
    return parser(payload)


@parse_payload.register
def _parse_bytes(payload: bytes, format=FileFormat.json):
    return parse_payload(payload.decode("utf-8", format))


@parse_payload.register
def _parse_path(payload: Path, format=FileFormat.json):
    file_format = payload.suffix
    if raw_format := _file_format_to_raw_format.get(file_format):
        if raw_format != format:
            logger.warning(f"overriding format: {format}->{file_format} {payload.name}")
            format = file_format.lstrip(".")
    else:
        logger.warning(f"attempting to parse a file {payload.name} as {format}")
    return parse_payload(payload.read_text(), format)


@parse_payload.register
def _parse_dict(payload: dict, format=FileFormat.json):
    return payload


@parse_payload.register
def _parse_list(payload: list, format=FileFormat.json):
    return payload


def get_parsers() -> Dict[Type[RegisteredPayloadT, PayloadParser]]:
    return _registered_parsers


def register_parser(
    payload_type: Type[RegisteredPayloadT], call: PayloadParser
) -> None:
    if previous := _registered_parsers.get(payload_type):
        raise PayloadParserAlreadyExistError(as_name(previous), as_name(call))
    _registered_parsers[payload_type] = call
    parser_name = as_name(call)
    logger.info(f"custom parser: {parser_name} for {payload_type}")
    parse_payload.register(call)
