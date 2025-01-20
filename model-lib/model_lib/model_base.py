from __future__ import annotations

from typing import Iterable, List, Type, TypeVar

from pydantic import BaseModel, RootModel
from zero_3rdparty.object_name import as_name
from zero_3rdparty.str_utils import want_bool

from model_lib.errors import ClsNameAlreadyExist, UnknownModelError
from model_lib.pydantic_utils import model_dump

T = TypeVar("T")
ModelT = TypeVar("ModelT", bound=BaseModel)
_model_name_to_type: dict[str, Type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": want_bool,  # type: ignore
}


def model_name_to_t(name: str) -> type:
    try:
        return _model_name_to_type[name]
    except KeyError as e:
        raise UnknownModelError(name) from e


class _Model(BaseModel):
    model_config = dict(
        use_enum_values=True,
        extra="allow",  # type: ignore
        arbitrary_types_allowed=True,
        populate_by_name=True,
    )

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls_name = cls.__name__
        if cls_name in ["Event", "Entity"]:
            return
        if old_cls := _model_name_to_type.get(cls_name) and not cls_name.startswith(
            "_"
        ):
            raise ClsNameAlreadyExist(as_name(cls), as_name(old_cls))
        _model_name_to_type[cls_name] = cls

    def __eq__(self, other):
        """cached properties are stored on the instance and shouldn't be
        included in comparison."""
        if not isinstance(other, BaseModel):
            return False
        return model_dump(self) == model_dump(other)


class Event(_Model):
    model_config = dict(frozen=True, validate_assignment=True)


class Entity(_Model):
    model_config = dict(frozen=False, validate_assignment=False)


class TypeEvent:
    @classmethod
    def __get_validators__(cls):
        yield cls.parse_by_type

    @classmethod
    def parse_by_type(cls, value: dict):
        if not isinstance(value, dict) or len(value) > 1:
            return value
        model_t, kwargs = value.popitem()
        ModelCls = model_name_to_t(model_t)
        return ModelCls(**kwargs)

    @classmethod
    def dump_list(cls, values: Iterable[object]) -> List[dict]:
        return [{type(event).__name__: event} for event in values]


SeqModelT = TypeVar("SeqModelT")


class SeqModel(RootModel[list[SeqModelT]]):
    def __iter__(self) -> Iterable[SeqModelT]:  # type: ignore
        return iter(self.root)

    def __getitem__(self, item):
        return self.root[item]

    def __len__(self):
        return len(self.root)
