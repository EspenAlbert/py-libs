import logging
from contextlib import suppress
from copy import deepcopy
from time import time
from typing import Any, Callable, TypeAlias
from uuid import uuid4

from model_lib.metadata import EventMetadata, current_metadata
from zero_lib.object_name import as_name

logger = logging.getLogger(__name__)
MetadataDumper = Callable[[dict], Any]
RemoveDumper: TypeAlias = Callable[[], None]
_dumpers: list[MetadataDumper] = []


def set_metadata_dumpers(*calls: MetadataDumper) -> None:
    global _dumpers
    _dumpers = list(calls)


def _no_removal():
    return None


def add_metadata_dumper(call: MetadataDumper) -> RemoveDumper:
    global _dumpers
    call_names = {as_name(call): call for call in _dumpers}
    call_name = as_name(call)
    if same_name_call := call_names.get(call_name):
        if same_name_call and same_name_call is call:
            logger.warning(f"metadat_dump_call_already_added={call_name}")
            return _no_removal
        _dumpers.remove(same_name_call)
    _dumpers.append(call)

    def remove():
        with suppress(ValueError):
            _dumpers.remove(call)

    return remove


def get_metadata_dumpers() -> list[MetadataDumper]:
    return _dumpers


def dump_metadata(skip_dumpers: bool = False) -> dict:
    metadata = current_metadata()
    dumped_metadata = deepcopy(metadata)
    if not skip_dumpers:
        for dumper in _dumpers:
            dumper(dumped_metadata)
    return dumped_metadata


class metadata_dumper:
    def __init__(
        self,
        static_dict: dict,
        dump_event_id: bool = True,
        dump_time: bool = True,
        extra_calls: list[MetadataDumper] = None,
        remove_existing: bool = False,
    ):
        self.calls = calls = [] if remove_existing else list(get_metadata_dumpers())
        if static_dict:

            def add_static_metadata(metadata: dict):
                metadata |= static_dict

            calls.append(add_static_metadata)
        if dump_event_id:

            def add_event_id(metadata: dict):
                metadata[EventMetadata.event_id] = uuid4().hex

            self.calls.append(add_event_id)
        if dump_time:

            def add_ts(metadata: dict):
                metadata[EventMetadata.dump_time] = time()

            self.calls.append(add_ts)
        calls.extend(extra_calls or [])

    def __enter__(self):
        self.old_dumpers = get_metadata_dumpers()
        set_metadata_dumpers(*self.calls)

    def __exit__(self, exc_type, exc_val, exc_tb):
        set_metadata_dumpers(*self.old_dumpers)
