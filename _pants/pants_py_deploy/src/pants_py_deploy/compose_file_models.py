from __future__ import annotations

from dataclasses import dataclass
from functools import total_ordering
from pathlib import Path
from typing import Any, Dict, Iterable, List, NamedTuple, Optional

from pydantic import Extra, Field, validator
from zero_3rdparty.datetime_utils import utc_now
from zero_3rdparty.dict_nested import read_nested_or_none
from zero_3rdparty.dict_utils import merge, sort_keys
from zero_3rdparty.iter_utils import first
from zero_3rdparty.iter_utils import ignore_falsy as ignore_falsy_method
from zero_3rdparty.iter_utils import key_equal_value_to_dict

from model_lib import Entity, Event, FileFormat, parse_payload, utc_datetime

NETWORK_NAME_DEFAULT = "wm-default"


class ContainerRunStatus(Event):
    container_id: str
    container_name: str
    is_running: bool
    started_at: utc_datetime
    # None when the container is still running
    exit_code: Optional[int]
    finished_at: Optional[utc_datetime]

    @property
    def is_finished(self) -> bool:
        return bool(not self.is_running and self.finished_at)

    @property
    def is_ok(self):
        return self.exit_code == 0

    @property
    def run_time_s(self) -> float:
        finished_at = self.finished_at or utc_now()
        return (finished_at - self.started_at).total_seconds()


class ContainerRunInfo(ContainerRunStatus):
    class Config:
        copy_on_model_validation = False

    stdout: List[str]
    stderr: List[str]


class ComposeServiceInfo(Entity):
    class Config:
        allow_mutation = True
        allow_population_by_field_name = True
        extra = Extra.allow

    image: Optional[str] = None
    labels: Dict[str, str] = Field(default_factory=dict)
    default_env: Dict[str, str] = Field(alias="environment", default_factory=dict)
    default_ports: List[str] = Field(alias="ports", default_factory=list)
    default_volumes: list[str] = Field(alias="volumes", default_factory=list)
    command: List[str] = Field(default_factory=list)

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
    ) -> dict:
        image = image or self.image
        assert image, "image unspecified"
        service_dict = {
            "image": image,
            "labels": sort_keys(self.labels),
            "environment": sort_keys(new_environment or self.default_env),
            "ports": port_overrides or self.default_ports if include_ports else [],
            "command": self.command,
            "volumes": self.default_volumes,
            "networks": [network_name] if network_name else [],
        }
        if ignore_falsy:
            return ignore_falsy_method(**service_dict)
        return service_dict


def read_service_name(compose_path: Path) -> str:
    parsed = parse_payload(compose_path, FileFormat.yaml)
    services: dict = parsed["services"]
    assert len(services) == 1
    return first(services)


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
    parsed: dict = parse_payload(compose_payload, FileFormat.yaml)
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
    return ComposeServiceInfo(
        image=image,
        labels=labels,
        default_env=env,
        default_ports=ports,
        command=command,
        default_volumes=volumes,
    )


def export_compose_dict(
    service_dict: dict,
    service_name: str,
    env_overrides: Optional[Dict[str, str]] = None,
    network_name: str | None = NETWORK_NAME_DEFAULT,
    volumes: Optional[List[str]] = None,
    add_labels: Dict[str, str] = None,
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


CONTAINER_ID_LENGTH = 8


def as_container_id(id_raw: str) -> str:
    return id_raw[:CONTAINER_ID_LENGTH]
