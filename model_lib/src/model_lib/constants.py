from pathlib import Path
from typing import Callable, TypeVar, Union

from zero_lib.enum_utils import StrEnum

RegisteredPayloadT = TypeVar("RegisteredPayloadT")
PayloadT = Union[RegisteredPayloadT, str, bytes, Path, dict, list]
ModelRawT = Union[dict, list]
METADATA_DUMP_KEY = "metadata"
MODEL_DUMP_KEY = "model"
METADATA_MODEL_NAME_FIELD = "model_name"
METADATA_MODEL_NAME_BACKUP_FIELD = "model_name_backup"


class FileFormat(StrEnum):
    json = "json"
    pretty_json = "pretty_json"
    yaml = "yaml"
    yml = "yml"


PayloadParser = Callable[[RegisteredPayloadT, FileFormat], ModelRawT]
