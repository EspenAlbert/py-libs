from __future__ import annotations

from typing import Type, TypeVar

from model_lib.constants import FileFormat, PayloadT
from pydantic.env_settings import SettingsError
from zero_lib.error import BaseError

T = TypeVar("T")


class UnknownModelError(BaseError):
    def __init__(self, model_name: str):
        self.model_name: str = model_name


class ClsNameAlreadyExist(BaseError):
    def __init__(self, new_cls_path: str, old_cls_path: str):
        self.new_cls_path = new_cls_path
        self.old_cls_path = old_cls_path


class NoDumper(Exception):
    def __init__(self, instance_type: Type[T]):
        self.instance_type = instance_type


class DumperExist(Exception):
    def __init__(self, existing_type: Type, new_type: Type):
        self.existing_type = existing_type
        self.new_type = new_type


class EnvVarParsingFailure(BaseError):
    def __init__(self, errors: list[SettingsError]):
        self.errors = errors


class ParseError(BaseError):
    pass


class PayloadParserNotFoundError(ParseError):
    def __init__(self, payload: object, format: FileFormat):
        self.payload = payload
        self.format = format


class PayloadError(ParseError):
    def __init__(self, payload: PayloadT, message: str, metadata: dict | None = None):
        self.message = message
        self.payload = payload
        self.metadata = metadata


class DumpConfigureError(BaseError):
    pass


class PayloadParserAlreadyExistError(DumpConfigureError):
    def __init__(self, old_call_name: str, new_call_name: str):
        self.old_call_name = old_call_name
        self.new_call_name = new_call_name
