from __future__ import annotations

import pydantic
from pydantic import BaseModel, RootModel, model_serializer
from zero_3rdparty.iter_utils import ignore_falsy

from model_lib import register_dumper


def base_model_dumper(model: BaseModel):
    if isinstance(model, RootModel):
        return model.root
    fields = model.model_fields  # type: ignore
    return {key: value for key, value in model if key in fields}


class IgnoreFalsy(BaseModel):
    @model_serializer(mode="wrap")
    def _ignore_falsy(
        self,
        nxt: pydantic.SerializerFunctionWrapHandler,
    ):
        serialized = nxt(self)
        no_falsy = ignore_falsy(**serialized)  # type: ignore
        return self.dump_dict_modifier(no_falsy)

    def dump_dict_modifier(self, payload: dict) -> dict:
        return payload


register_dumper(BaseModel, base_model_dumper)
