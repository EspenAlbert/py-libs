from collections import ChainMap
from itertools import chain
from typing import Iterable

from compose_chart_export.ports import PrefixPort
from docker_compose_parser.file_models import (
    ComposeServiceInfo,
    export_compose_dict_from_services,
    iter_compose_info,
)
from pants.engine.fs import FileContent
from pants_py_deploy.fields import COMPOSE_NETWORK_NAME
from pants_py_deploy.models import ComposeFiles, ComposeService, FileEnvVars
from zero_3rdparty.str_utils import ensure_suffix

from model_lib import FileFormat, dump, parse_payload


def create_compose_files(
    new_paths: set[str], compose_files: ComposeFiles
) -> list[FileContent]:
    new_files = []
    path_to_service = compose_files.paths_managed
    for path in new_paths:
        compose_services = path_to_service[path]
        compose_yaml = as_new_compose_yaml(compose_services)
        new_files.append(create_compose_file(path, compose_yaml))
    return new_files


def as_new_compose_yaml(compose_services: Iterable[ComposeService]) -> str:
    service_dicts = _as_service_dicts(compose_services)
    compose_full_dict = export_compose_dict_from_services(
        service_dicts, network_name=COMPOSE_NETWORK_NAME
    )
    compose_yaml = dump(compose_full_dict, FileFormat.yaml)
    return compose_yaml


def _as_service_dicts(compose_services: Iterable[ComposeService]) -> dict[str, dict]:
    return {service.name: _as_service_dict(service) for service in compose_services}


def _as_service_dict(compose_service: ComposeService) -> dict:
    service_info = ComposeServiceInfo(
        image=compose_service.image_url,
        default_env={**compose_service.env_vars},
        default_ports=file_compose_ports(compose_service.ports),
        default_volumes=[],
        command=[],
        labels={"chart_name": compose_service.chart_inferred_name}
        if compose_service.chart_path
        else {},
    )
    return service_info.as_service_dict(
        ignore_falsy=True, include_ports=True, network_name=COMPOSE_NETWORK_NAME
    )


def modify_existing_compose(
    compose_files: ComposeFiles,
    digest_contents: Iterable[FileContent],
) -> list[FileContent]:
    new_contents = []
    for file_content in digest_contents:
        path = file_content.path
        if not compose_files.is_managed(path):
            new_contents.append(file_content)
            continue
        compose_services = compose_files.paths_managed[path]
        compose_yaml = as_compose_yaml(compose_services, file_content)
        new_contents.append(create_compose_file(path, compose_yaml))
    return new_contents


def as_compose_yaml(
    compose_services: Iterable[ComposeService], file_content: FileContent
) -> str:
    existing_full = parse_payload(file_content.content, FileFormat.yaml)
    existing_infos = dict(iter_compose_info(file_content.content))
    managed_service_dicts = _as_service_dicts(compose_services)
    for service_name, service_dict in managed_service_dicts.items():
        if existing_info := existing_infos.get(service_name):
            new_dictionary = existing_info.as_service_dict(
                image=service_dict["image"],
                include_ports=True,
                port_overrides=service_dict.get("ports", []),
                ignore_falsy=True,
                new_environment=service_dict.get("environment", {}),
                network_name=COMPOSE_NETWORK_NAME,
                ensure_labels=service_dict.get("labels", {}),
            )
            existing_full["services"][service_name] = new_dictionary
        else:
            existing_full["services"][service_name] = service_dict
    compose_yaml = dump(existing_full, FileFormat.yaml)
    return compose_yaml


def create_compose_file(path: str, content: str) -> FileContent:
    return FileContent(
        path=ensure_suffix(path, "/docker-compose.yaml"),
        content=content.encode("utf-8"),
    )


def file_env_vars(env_vars: FileEnvVars, dependencies: Iterable[str]) -> dict[str, str]:
    env_vars_paths = set(dependencies) & env_vars.file_env_vars.keys()
    file_env_vars = ChainMap(
        *[
            {env.name: env.default for env in env_vars.file_env_vars[env_file]}
            for env_file in env_vars_paths
        ]
    )
    return {**file_env_vars}


def file_compose_ports(ports: Iterable[PrefixPort]) -> list[str]:
    return [f"{port.port}:{port.port}" for port in ports]


def combined_ports(
    env_vars: FileEnvVars, dependencies: Iterable[str]
) -> Iterable[PrefixPort]:
    return chain.from_iterable(
        env_vars.file_port_info.get(port_file, []) for port_file in dependencies
    )
