from __future__ import annotations

from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def load_yaml_model(path: Path, model_type: type[T]) -> T:
    data = yaml.safe_load(path.read_text())
    return model_type.model_validate(data)


def dump_yaml_model(model: BaseModel) -> str:
    data = model.model_dump(mode="json", exclude_none=True)
    return yaml.safe_dump(data, default_flow_style=False, sort_keys=False)
