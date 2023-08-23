from __future__ import annotations

from functools import cached_property
from typing import Generic, Iterable, List, Sequence, Type, TypeVar

from pydantic import BaseModel, ConfigDict, Extra

from model_lib.errors import ClsNameAlreadyExist, UnknownModelError
from model_lib.pydantic_utils import IS_PYDANTIC_V2, model_dump
from zero_3rdparty.object_name import as_name
from zero_3rdparty.str_utils import want_bool

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
    if IS_PYDANTIC_V2:
        model_config = ConfigDict(  # type: ignore
            use_enum_values=True,
            extra=Extra.allow,
            arbitrary_types_allowed=True,
            populate_by_name=True,
        )
    else:

        class Config:
            use_enum_values = True
            extra = Extra.allow
            arbitrary_types_allowed = True
            keep_untouched = (cached_property, Exception)
            allow_population_by_field_name = True

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

    if IS_PYDANTIC_V2:

        def __eq__(self, other):
            """cached properties are stored on the instance and shouldn't be
            included in comparison."""
            if not isinstance(other, BaseModel):
                return False
            return model_dump(self) == model_dump(other)

    else:

        def __eq__(self, other):
            if not isinstance(other, BaseModel):
                return False
            fields = self.__fields__
            return model_dump(self, include=fields.keys()) == model_dump(
                other, include=fields.keys()
            )


class Event(_Model):
    if IS_PYDANTIC_V2:
        model_config = ConfigDict(frozen=True, validate_assignment=True)
    else:

        class Config:
            allow_mutation = False


class Entity(_Model):
    if IS_PYDANTIC_V2:
        model_config = ConfigDict(frozen=False, validate_assignment=False)
    else:

        class Config:
            allow_mutation = True


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


if IS_PYDANTIC_V2:
    from pydantic import RootModel  # type: ignore

    SeqModelT = TypeVar("SeqModelT")

    class SeqModel(RootModel[list[SeqModelT]], Generic[SeqModelT]):
        def __iter__(self) -> Iterable[SeqModelT]:  # type: ignore
            return iter(self.root)

        def __getitem__(self, item):
            return self.root[item]

        def __len__(self):
            return len(self.root)

else:

    class SeqModel(_Model, Generic[T]):  # type: ignore
        __root__: Sequence[T]

        def __init_subclass__(cls, **kwargs):
            assert "__root__" in cls.__fields__

        def __iter__(self) -> Iterable[T]:  # type: ignore
            return iter(self.__root__)

        def __getitem__(self, item):
            return self.__root__[item]

        def __len__(self):
            return len(self.__root__)
