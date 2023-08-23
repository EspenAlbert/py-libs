from pathlib import Path
from typing import Callable, TypeVar, Union

from zero_3rdparty.enum_utils import StrEnum

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
    json_pretty = "pretty_json"
    yaml = "yaml"
    yml = "yml"
    # only recommended to use with pydantic2
    json_pydantic = "json_pydantic"
    pydantic_json = "pydantic_json"
    # pip install tomlkit
    toml = "toml"
    toml_compact = "toml_compact"


PayloadParser = Callable[[RegisteredPayloadT, Union[FileFormat, str]], ModelRawT]
