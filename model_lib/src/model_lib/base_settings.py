"""This module is used for handling settings in a consistent way throughout the
code base.

When should you create a settings.py?
-------------------------------------
1. You have something that depends on the runtime environment (host-machine | docker, testing | prod, etc.)
2. You want to offer some flexibility in how the application behaves based on env_vars

Notice that (2) can be taken too far.
There is a cognitive overhead in having too many env_vars.

How is the settings variable determined at runtime? (connect to rabbitmq example)
---------------------------------------------------------------------------------
Suppose there is a ```def connect_to_rabbitmq(url: str)```
There are a few ways of passing in the url:

1. ```connect_to_rabbitmq('overriding_url')
- This solution is independent of settings and env_vars and is the most deterministic approach
- Prefer this method when you don't need the flexibility of changing the code based on environment

2.  ```python
    settings = RabbitmqSettings()
    # Later in the code
    connect_to_rabbitmq(settings.url)
    ```
- This solution depends on the environment variables the moment the settings are created and will never change.
- E.g., when an app runs in production the env_vars are not expected to change. Therefore, creating the settings once is preferred.


How to define a variable default which is different in localhost/container environment?
------------------------------------------------------------------------------------
Use a rabbitmq_url: str = container_or_default('amqp://guest:guest@rabbitmq:5672', 'amqp://guest:guest@localhost:5672')
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from json import dumps
from pathlib import Path
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union

from model_lib.errors import EnvVarParsingFailure
from model_lib.pydantic_utils import field_names
from pydantic import BaseSettings, Field, root_validator
from pydantic.env_settings import SettingsError
from zero_lib.iter_utils import first
from zero_lib.run_env import running_in_container_environment
from zero_lib.str_utils import words_to_list

logger = logging.getLogger(__name__)


def env_value_as_str(value: Any) -> str | None:
    if value is None:
        return
    if isinstance(value, (Path, bool, float, int)):
        value = str(value)
    if isinstance(value, (list, dict)):
        value = json.dumps(value)
    assert isinstance(value, str), f"env value must be str, was {value!r}"
    return value


def set_env_value(settings: Type[BaseSettings], field_name: str, value: str) -> None:
    if value := env_value_as_str(value):
        key = env_var_name(settings, field_name)
        os.environ[key] = value


def set_all_env_values(settings: BaseSettings):
    for field_name in settings.__fields__:
        set_env_value(type(settings), field_name, getattr(settings, field_name))


class BaseEnvVars(BaseSettings):
    @classmethod
    def env_var_name(cls, field_name: str) -> str:
        model_field = cls.__fields__[field_name]
        extras: dict = model_field.field_info.extra
        if env := extras.get("env"):
            return env
        return first(extras["env_names"], str)

    def as_env_dict(self) -> dict[str, str]:
        values = {}
        for field_name in self.__fields__.keys():
            value_raw = getattr(self, field_name, None)
            if value := env_value_as_str(value_raw):
                env_name = self.env_var_name(field_name)
                values[env_name] = value
        return values

    def _build_values(
        self,
        init_kwargs: Dict[str, object],
        _env_file: Union[Path, str, None] = None,
        _env_file_encoding: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, object]:
        """Enables env_vars that are lists/sets to be specified as a space-
        separated list instead of json_encoded.

        pydantic expects all complex value (lists/sets/dicts/etc.) to be
        json encoded and fails if they are not. This method makes
        another attempts to parse by splitting strings to lists based on
        whitespace and then encoding it back to the env_var so pydantic
        will succeed on the next attempt
        """
        errors: List[SettingsError] = []
        for _ in self.__fields__:  # one attempt for each model field
            try:
                return super()._build_values(
                    init_kwargs, _env_file, _env_file_encoding, **kwargs
                )
            except SettingsError as error:
                field = decode_settings_error(error)
                env_value = os.environ[field]
                if env_value.startswith(("[", "{", '"')):  # probably a json
                    logger.warning(f"malformed env_var value for {field}={env_value}")
                    errors.append(error)
                    break
                as_list = words_to_list(env_value) if env_value else []
                os.environ[field] = dumps(as_list)
        if not errors:
            return super()._build_values(
                init_kwargs, _env_file, _env_file_encoding, **kwargs
            )
        logger.warning(repr(errors))
        raise EnvVarParsingFailure(errors)

    @root_validator(pre=True)
    def replace_none_str_with_none(cls, values: dict):
        def replace_none(value):
            if isinstance(value, str) and value == "None":
                return None
            return value

        return {key: replace_none(value) for key, value in values.items()}


T = TypeVar("T")


def container_or_default(container_default: T, cls_default: T) -> Field:
    return Field(
        default_factory=DockerOrClsDefDefault(
            docker_default=container_default, cls_default=cls_default
        )
    )


@dataclass
class DockerOrClsDefDefault(Generic[T]):
    docker_default: T
    cls_default: T

    def __call__(self) -> T:
        if running_in_container_environment():
            return self.docker_default
        return self.cls_default


def decode_settings_error(error: SettingsError) -> str:
    """
    >>> decode_settings_error(SettingsError('error parsing JSON for "my_env_list_name"'))
    'my_env_list_name'
    """
    message: str = error.args[0]
    error_text, error_field, empty = message.split('"')
    return error_field


def port_info(number: int, *, url_prefix: str, protocol: str) -> Field:
    """Used for pants plugin "artifacts" to know which url_prefix and protocol
    to use in Chart."""
    return Field(default=number)


def env_var_name(
    settings: Union[BaseSettings, Type[BaseSettings]], field_name: str
) -> str:
    model_field = settings.__fields__.get(field_name)
    assert model_field, f"{settings}.{field_name} NOT FOUND"
    extra_info = model_field.field_info.extra
    if env := extra_info.get("env"):
        return env
    return first(extra_info["env_names"], str)


def env_var_names(settings: BaseSettings | Type[BaseSettings]) -> list[str]:
    return [env_var_name(settings, field_name) for field_name in field_names(settings)]
