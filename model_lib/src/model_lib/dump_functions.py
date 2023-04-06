from __future__ import annotations

from functools import partial
from typing import Callable, Optional, Type

from pydantic import BaseModel
from zero_lib.iter_utils import ignore_falsy_recurse

from model_lib import ModelT, register_dumper


def base_model_dumper(model: BaseModel):
    """Why not use model.json()?

    Avoid having __root__ keys in the json and support our own defaults
    and dumping cached_properties, see test_dump_functions.py
    """
    field_names = model.__fields__
    if "__root__" in field_names:
        return model.__root__
    return model.dict()


def _dump_no_falsy(
    model: BaseModel,
    extra_dict_kwargs: dict,
    by_alias: bool = False,
    exclude_unset: bool = True,
):
    extra_dict_kwargs.setdefault("by_alias", by_alias)
    extra_dict_kwargs.setdefault("exclude_unset", exclude_unset)
    return ignore_falsy_recurse(**BaseModel.dict(model, **extra_dict_kwargs))


def dump_ignore_falsy(
    cls: Optional[Type[ModelT]] = None,
    by_alias: bool = False,
    exclude_unset: bool = True,
    extra_dump: Callable[[dict], dict] | None = None,
):
    """Notice, this is a cls decorator.

    @dump_ignore_falsy
    class SomeClass(Event):
        name: str
    """

    def inner(_actual_class: Type[ModelT]) -> Type[ModelT]:
        dump_call = partial(
            _dump_no_falsy, by_alias=by_alias, exclude_unset=exclude_unset
        )
        if extra_dump:

            def new_dict(self, **extra_dict_kwargs):
                as_dict = dump_call(self, extra_dict_kwargs)
                return extra_dump(as_dict)

        else:

            def new_dict(self, **extra_dict_kwargs):
                return dump_call(self, extra_dict_kwargs)

        _actual_class.dict = new_dict
        return _actual_class

    return inner(cls) if cls else inner


register_dumper(BaseModel, base_model_dumper)
