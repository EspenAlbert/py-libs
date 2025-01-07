from __future__ import annotations

from functools import partial
from typing import Callable, Optional, Type

from pydantic import BaseModel

from model_lib import ModelT, register_dumper
from model_lib.pydantic_utils import IS_PYDANTIC_V2, model_dump
from zero_3rdparty.iter_utils import ignore_falsy_recurse

if IS_PYDANTIC_V2:
    from pydantic import RootModel  # type: ignore

    def base_model_dumper(model: BaseModel):
        if isinstance(model, RootModel):
            return model.root
        fields = model.model_fields  # type: ignore
        return {key: value for key, value in model if key in fields}

else:

    def base_model_dumper(model: BaseModel):
        """Why not use model.json()?

        Avoid having __root__ keys in the json and support our own
        defaults and dumping cached_properties, see
        test_dump_functions.py
        """

        if root := getattr(model, "__root__", None):
            return root
        fields = model.__fields__
        return {key: value for key, value in model if key in fields}


def _dump_no_falsy(
    model: BaseModel,
    extra_dict_kwargs: dict,
    by_alias: bool = False,
    exclude_unset: bool = True,
):
    extra_dict_kwargs.setdefault("by_alias", by_alias)
    extra_dict_kwargs.setdefault("exclude_unset", exclude_unset)
    before_ignore = model_dump(model, **extra_dict_kwargs)
    return ignore_falsy_recurse(**before_ignore)


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
            _dump_no_falsy,
            by_alias=by_alias,
            exclude_unset=exclude_unset,
            extra_dict_kwargs={},
        )
        if extra_dump:

            def dump_and_call(self):
                as_dict = dump_call(self)
                return extra_dump(as_dict)

            register_dumper(_actual_class, dump_and_call)
        else:
            register_dumper(_actual_class, dump_call)
        return _actual_class

    return inner(cls) if cls else inner


register_dumper(BaseModel, base_model_dumper)
