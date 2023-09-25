from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import total_ordering
from pathlib import Path
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Union

from pydantic import Extra, Field

from model_lib import Entity, FileFormat, parse_payload
from model_lib.pydantic_utils import IS_PYDANTIC_V2
from zero_3rdparty.dict_nested import read_nested_or_none
from zero_3rdparty.dict_utils import merge, sort_keys
from zero_3rdparty.iter_utils import ignore_falsy as ignore_falsy_method
from zero_3rdparty.iter_utils import key_equal_value_to_dict
from zero_3rdparty.timeparse import timeparse

NETWORK_NAME_DEFAULT = "compose-default"


class ComposeHealthCheck(Entity):
    test: Union[str, list[str]]
    interval: str = "30s"
    timeout: str = "30s"
    start_period: str = "0s"
    # https://github.com/docker/compose/issues/10830
    # start_interval: str = "5s"
    retries: int = 3

    @property
    def command_list(self) -> list[str]:
        if isinstance(self.test, list):
            return [part for part in self.test if part not in ("CMD", "CMD-SHELL")]
        return self.test.split(" ")

    @property
    def interval_seconds(self) -> int:
        return timeparse(self.interval)

    @property
    def timeout_seconds(self) -> int:
        return timeparse(self.timeout)

    @property
    def start_period_seconds(self) -> int:
        return timeparse(self.start_period)

    @classmethod
    def parse_healthcheck(cls, raw: Any) -> ComposeHealthCheck | None:
        if isinstance(raw, ComposeHealthCheck):
            return raw
        if raw is None:
            return raw
        if not isinstance(raw, dict):
            try:
                raw = dict(raw)
            except Exception as e:
                raise ValueError(
                    f"cannot parse healthcheck from {raw!r}, need dict"
                ) from e
        # keep in sync with py_deploy
        raw = deepcopy(raw)
        test_value = raw.get("test")
        if not test_value:
            port = int(raw.pop("port"))
            path = str(raw.pop("path", "/"))
            raw["test"] = f"curl -f http://localhost:{port}{path} || exit 1"
        raw["retries"] = int(raw.get("retries", 3))
        raw = {key.replace("-", "_"): value for key, value in raw.items()}
        raw.pop(
            "start_interval", None
        )  # https://github.com/docker/compose/issues/10830
        return cls(**raw)


class ComposeServiceInfo(Entity):
    if IS_PYDANTIC_V2:
        model_config = dict(populate_by_name=True, extra=Extra.allow)  # type: ignore
    else:

        class Config:
            allow_population_by_field_name = True
            extra = Extra.allow

    image: Optional[str] = None
    labels: Dict[str, str] = Field(default_factory=dict)
    default_env: Dict[str, str] = Field(alias="environment", default_factory=dict)
    default_ports: List[str] = Field(alias="ports", default_factory=list)
    default_volumes: list[str] = Field(alias="volumes", default_factory=list)
    command: List[str] = Field(default_factory=list)
    healthcheck: Optional[ComposeHealthCheck] = None

    if IS_PYDANTIC_V2:
        from pydantic import field_validator  # type: ignore

        @field_validator("command", mode="before")
        def split_str(cls, value: Any) -> list[str]:
            if isinstance(value, str):
                return value.split()
            return value

        @field_validator("default_env", mode="before")
        def parse_list(cls, value):
            if isinstance(value, list):
                value = key_equal_value_to_dict(value)
            # pydantic v2 will not "convert" values to strings
            return {k: str(v) for k, v in value.items()}

        @field_validator("healthcheck", mode="before")
        def parse_healthcheck(cls, value: dict):
            return ComposeHealthCheck.parse_healthcheck(value)

    else:
        from pydantic import validator  # type: ignore

        @validator("command", pre=True)
        def split_str(cls, value: Any) -> list[str]:
            if isinstance(value, str):
                return value.split()
            return value

        @validator("default_env", pre=True)
        def parse_list(cls, value):
            if isinstance(value, list):
                return key_equal_value_to_dict(value)
            return value

        @validator("healthcheck", pre=True)
        def parse_healthcheck(cls, value: dict):
            return ComposeHealthCheck.parse_healthcheck(value)

    @property
    def host_container_ports(self) -> Iterable[tuple[int, int]]:
        for port in self.default_ports:
            host, container = port.split(":")
            yield int(host), int(container)

    def as_service_dict(
        self,
        image: str | None = None,
        include_ports: bool = False,
        port_overrides: list[str] | None = None,
        ignore_falsy: bool = False,
        new_environment: dict | None = None,
        network_name: str = "",
        ensure_labels: dict[str, str] | None = None,
        healthcheck: dict | None = None,
    ) -> dict:
        healthcheck = healthcheck or self.healthcheck  # type: ignore
        image = image or self.image
        assert image, "image unspecified"
        existing_labels = sort_keys(self.labels)
        if ensure_labels:
            existing_labels.update(ensure_labels)
        service_dict = {
            "image": image,
            "labels": existing_labels,
            "environment": sort_keys(new_environment or self.default_env),
            "ports": port_overrides or self.default_ports if include_ports else [],
            "command": self.command,
            "volumes": self.default_volumes,
            "networks": [network_name] if network_name else [],
        }
        if healthcheck:
            parsed_healthcheck = ComposeHealthCheck.parse_healthcheck(healthcheck)
            if IS_PYDANTIC_V2:
                service_dict["healthcheck"] = parsed_healthcheck.model_dump()  # type: ignore
            else:
                service_dict["healthcheck"] = parsed_healthcheck.dict()  # type: ignore
        if ignore_falsy:
            return ignore_falsy_method(**service_dict)
        return service_dict


class ServiceNameInfo(NamedTuple):
    name: str
    info: ComposeServiceInfo


def iter_compose_info(
    compose_payload: str | Path | bytes,
) -> Iterable[tuple[str, ComposeServiceInfo]]:
    parsed = parse_payload(compose_payload, FileFormat.yaml)
    assert isinstance(parsed, dict)
    services = parsed["services"]
    assert isinstance(services, dict)
    for name, service_dict in services.items():
        info = ComposeServiceInfo(**service_dict)
        yield ServiceNameInfo(name, info)


@total_ordering
@dataclass
class _NameDict:
    name: str
    service_dict: dict
    index: int

    def depends_on(self, name: str) -> bool:
        depends_on = self.service_dict.get("depends_on", [])
        return name in list(depends_on)

    def __lt__(self, other):
        if not isinstance(other, _NameDict):
            raise TypeError
        return other.depends_on(self.name) or self.index < other.index


def iter_sorted_services(compose_payload: str | Path) -> list[tuple[str, dict]]:
    """`depends_on` if used if it exists, otherwise services are sorted by
    their order in the file."""
    parsed = parse_payload(compose_payload, FileFormat.yaml)
    assert isinstance(parsed, dict)
    services: dict = parsed["services"]
    services_sorted = sorted(
        _NameDict(name, d, i) for i, (name, d) in enumerate(services.items())
    )
    return [(service.name, service.service_dict) for service in services_sorted]


def read_compose_info(compose_path: Path, service_name: str) -> ComposeServiceInfo:
    parsed = parse_payload(compose_path, FileFormat.yaml)
    image = read_nested_or_none(parsed, f"services.{service_name}.image")
    labels = read_nested_or_none(parsed, f"services.{service_name}.labels") or {}
    env = read_nested_or_none(parsed, f"services.{service_name}.environment") or {}
    ports = read_nested_or_none(parsed, f"services.{service_name}.ports") or []
    command = read_nested_or_none(parsed, f"services.{service_name}.command") or []
    volumes = read_nested_or_none(parsed, f"services.{service_name}.volumes") or []
    healthcheck = read_nested_or_none(parsed, f"services.{service_name}.healthcheck")
    return ComposeServiceInfo(
        image=image,  # type: ignore
        labels=labels,  # type: ignore
        default_env=env,  # type: ignore
        default_ports=ports,  # type: ignore
        command=command,  # type: ignore
        default_volumes=volumes,  # type: ignore
        healthcheck=healthcheck,  # type: ignore
    )


def export_compose_dict(
    service_dict: dict,
    service_name: str,
    env_overrides: Optional[Dict[str, str]] = None,
    network_name: str | None = NETWORK_NAME_DEFAULT,
    volumes: Optional[List[str]] = None,
    add_labels: Dict[str, str] | None = None,
    command: Optional[List[str]] = None,
    only_override_existing_env_vars: bool = True,
    network_external: bool = True,
) -> dict:
    """Valid dictionary for a docker-compose.yaml file."""
    service_dict.pop("depends_on", "")
    if network_name:
        service_dict["networks"] = [network_name]
    if env_overrides:
        env = service_dict["environment"]
        merge(
            env,
            env_overrides,
            allow_overwrite=True,
            allow_new=not only_override_existing_env_vars,
        )
        service_dict["environment"] = sort_keys(env)
    if volumes:
        service_dict["volumes"] = volumes
    if command:
        service_dict["command"] = command
    add_labels = add_labels or {}
    if add_labels:
        original_labels = service_dict.setdefault("labels", {})
        original_labels.update(add_labels)
    compose_dict = dict(version="3", services={service_name: service_dict})
    if network_name:
        compose_dict["networks"] = {network_name: dict(external=network_external)}
    return compose_dict


def export_compose_dict_from_services(
    service_dicts: dict[str, dict], network_name: str
):
    name, service_dict = service_dicts.popitem()
    full_compose = export_compose_dict(
        service_dict=service_dict, service_name=name, network_name=network_name
    )
    for other_service, other_service_dict in service_dicts.items():
        full_compose["services"][other_service] = other_service_dict
    return full_compose
