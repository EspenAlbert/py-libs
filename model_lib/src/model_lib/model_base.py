from __future__ import annotations

from functools import cached_property
from typing import (
    TYPE_CHECKING,
    Generic,
    Iterable,
    List,
    Sequence,
    Type,
    TypeVar,
    Union,
)

from model_lib.errors import ClsNameAlreadyExist, UnknownModelError
from pydantic import BaseModel, Extra
from zero_3rdparty.object_name import as_name
from zero_3rdparty.str_utils import want_bool

if TYPE_CHECKING:
    from pydantic.typing import AbstractSetIntStr, DictStrAny, MappingIntStrAny

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
    class Config:
        use_enum_values = True
        extra = Extra.allow
        arbitrary_types_allowed = True
        keep_untouched = (cached_property, Exception)

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
        return self.dict() == other.dict()

    def dict(
        self,
        *,
        include: Union["AbstractSetIntStr", "MappingIntStrAny"] = None,  # type: ignore
        exclude: Union["AbstractSetIntStr", "MappingIntStrAny"] = None,  # type: ignore
        by_alias: bool = False,
        skip_defaults: bool = None,  # type: ignore
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
    ) -> "DictStrAny":  # noqa
        return super().dict(
            include=include or self.__fields__.keys(),
            exclude=exclude,
            by_alias=by_alias,
            skip_defaults=skip_defaults,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )


class Event(_Model):
    class Config:
        allow_mutation = False


class Entity(_Model):
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


class SeqModel(_Model, Generic[T]):
    __root__: Sequence[T]

    def __init_subclass__(cls, **kwargs):
        assert "__root__" in cls.__fields__

    def __iter__(self) -> Iterable[T]:  # type: ignore
        return iter(self.__root__)

    def __getitem__(self, item):
        return self.__root__[item]

    def __len__(self):
        return len(self.__root__)
