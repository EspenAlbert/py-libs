from __future__ import annotations

import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Iterable

import semver
from compose_chart_export.chart_export import export_chart
from compose_chart_export.chart_file_templates import (
    ChartTemplateSpec,
    HostPathContainerPath,
    PersistentVolume,
    TemplateReplacements,
    kubernetes_label_regex,
)
from compose_chart_export.chart_mods import (
    add_container,
    update_containers,
    update_services,
    update_values,
)
from compose_chart_export.chart_read import container_template
from compose_chart_export.ports import PortProtocol, PrefixPort
from compose_chart_export.settings import ChartTemplate
from docker_compose_parser.file_models import (
    ComposeServiceInfo,
    iter_compose_info,
    read_compose_info,
)
from model_lib.serialize.yaml_serialize import edit_yaml
from pydantic import BaseModel
from zero_3rdparty.file_utils import PathLike, copy
from zero_3rdparty.str_utils import want_bool

from model_lib import FileFormat, parse_model, parse_payload

logger = logging.getLogger(__name__)


def parse_template_name(labels: dict) -> ChartTemplate | None:
    return labels.get("chart_template")


def parse_target_volumes(labels: dict) -> list[HostPathContainerPath]:
    if raw := labels.get("chart_target_volumes"):
        as_list = parse_payload(raw, FileFormat.json)
        return [parse_model(each, t=HostPathContainerPath) for each in as_list]
    return []


def parse_persistent_volumes(labels: dict[str, str]) -> list[PersistentVolume]:
    if raw := labels.get("chart_persistent_volumes"):
        as_list = parse_payload(raw, FileFormat.json)
        return [parse_model(each, t=PersistentVolume) for each in as_list]
    return []


def parse_use_resource_limits(labels: dict[str, str]) -> bool:
    return want_bool(labels.get("chart_use_resource_limits", False))


def parse_repo_name(labels: dict[str, str]) -> str:
    return labels.get("chart_repo_name", "")


def parse_repo_owner(labels: dict[str, str]) -> str:
    return labels.get("chart_repo_owner", "")


def parse_existing_chart(labels: dict[str, str]):
    return labels.get("chart_path", "")


def parse_service_account_name(labels: dict[str, str]):
    return labels.get("chart_service_account_name", "")


class ExtraContainer(BaseModel):
    name: kubernetes_label_regex
    env: dict[str, str]
    command: list[str]


def parse_service_name_extra_containers(
    compose_path: Path,
) -> tuple[str, list[ExtraContainer]]:
    extra_containers = []
    service_names = []
    service_names_with_chart_name = []
    for each_service_name, info in iter_compose_info(compose_path):
        if info.labels.get("extra_container") == "true":
            container_name = each_service_name.replace("_", "-")
            extra_containers.append(
                ExtraContainer(
                    name=container_name, env=info.default_env, command=info.command
                )
            )
        elif info.labels.get("chart_name"):
            service_names_with_chart_name.append(each_service_name)
        else:
            service_names.append(each_service_name)
    if service_names_with_chart_name:
        service_names = service_names_with_chart_name
    if not service_names:
        raise ValueError(f"No main service name found in {compose_path}")
    if len(service_names) > 1:
        raise ValueError(
            f"Possibly more than 1 service as the main service: {service_names}, {compose_path}"
        )
    return service_names[0], extra_containers


def ensure_chart_version_valid(chart_version: str):
    """
    >>> ensure_chart_version_valid("v0.1.0-amd")
    'v0.1.0-amd'
    >>> ensure_chart_version_valid("v0.0.1")
    'v0.0.1'
    >>> ensure_chart_version_valid("latest-amd")
    '0.0.1-latest-amd'
    """
    check_version = chart_version if chart_version[0].isdigit() else chart_version[1:]
    try:
        semver.parse_version_info(check_version)
        return chart_version
    except ValueError:
        updated_version = f"0.0.1-{chart_version}"
        logger.warning(
            f"not a valid semver: {chart_version}, will try: {updated_version}"
        )
    semver.parse_version_info(updated_version)
    return updated_version


def export_from_compose(
    compose_path: PathLike,
    chart_version: str,
    chart_name: str,
    image_url: str = "unset",
    on_exported: Callable[[Path], None] | None = None,
    use_chart_name_as_container_name: bool = True,
):
    chart_version = ensure_chart_version_valid(chart_version)
    compose_path = Path(compose_path)
    service_name, extra_containers = parse_service_name_extra_containers(compose_path)
    info = read_compose_info(compose_path, service_name)
    env = info.default_env
    compose_labels = info.labels
    prefix_ports = parse_container_ports(compose_labels, info.host_container_ports)
    container_name = (
        chart_name.replace("_", "-")
        if use_chart_name_as_container_name
        else service_name.replace("_", "-")
    )
    with TemporaryDirectory() as path:
        chart_path = Path(path) / chart_name
        if existing_chart := parse_existing_chart(compose_labels):
            existing_chart = (compose_path.parent / existing_chart).resolve()
            assert (
                existing_chart.exists()
            ), f"existing chart not found @ {existing_chart}"
            copy(existing_chart, chart_path)
            with edit_yaml(chart_path / "Chart.yaml") as chart_info:
                chart_info["appVersion"] = chart_version
                chart_info["version"] = chart_version
        else:
            template_name, spec = create_spec(
                chart_name, container_name, chart_version, service_name, info
            )
            export_chart(spec, template_name, chart_path)
        update_values(
            chart_path, env, container_name=container_name, set_image=image_url
        )
        command = info.command
        if not command:
            logger.info(f"no command for: {service_name} @ {compose_path}")
        container_template_path = container_template(chart_path)
        update_containers(
            chart_path,
            env,
            prefix_ports,
            container_name=container_name,
            command=command,
            rel_path=container_template_path,
            env_vars_field_refs={},
        )
        if prefix_ports:
            update_services(chart_path, prefix_ports, container_name=container_name)
        if extra_containers:
            for container in extra_containers:
                add_container(
                    chart_dir=chart_path,
                    container_name=container.name,
                    rel_path=container_template_path,
                )
                update_containers(
                    chart_dir=chart_path,
                    env_vars=container.env,
                    ports=[],
                    container_name=container.name,
                    command=container.command,
                    rel_path=container_template_path,
                    env_vars_field_refs={},
                )
                update_values(
                    chart_path,
                    container.env,
                    container_name=container.name,
                    set_image="unset",
                )
        if on_exported:
            on_exported(chart_path)


def parse_container_ports(
    compose_labels: dict[str, str], ports: Iterable[tuple[int, int]]
) -> list[PrefixPort]:
    prefix_ports = []
    for _, container_port in ports:
        port_protocol = compose_labels.get(
            f"PORT_PROTOCOL_{container_port}", PortProtocol.http
        )
        prefix_port = PrefixPort(
            prefix="/", port=container_port, protocol=port_protocol
        )
        prefix_ports.append(prefix_port)
    return prefix_ports


def create_spec(
    chart_name: str,
    container_name: str,
    chart_version: str,
    service_name: str,
    info: ComposeServiceInfo,
) -> tuple[str, ChartTemplateSpec]:
    compose_labels = info.labels
    template_name = parse_template_name(compose_labels)
    ports = list(info.host_container_ports)
    if ports:
        template_name = template_name or ChartTemplate.SERVICE_DEPLOYMENT
    else:
        logger.info(f"no ports for {service_name}")
        template_name = template_name or ChartTemplate.DEPLOYMENT_ONLY
    target_volumes = parse_target_volumes(compose_labels)
    persistent_volumes = parse_persistent_volumes(compose_labels)
    use_resource_limits = parse_use_resource_limits(compose_labels)
    repo_name = parse_repo_name(compose_labels) or container_name
    repo_owner = parse_repo_owner(compose_labels) or "unknown"
    service_account_name = parse_service_account_name(compose_labels)
    return template_name, ChartTemplateSpec(
        replacements=TemplateReplacements(
            APP_VERSION=chart_version,
            CHART_VERSION=chart_version,
            REPO_NAME=repo_name,
            REPO_OWNER=repo_owner,
            APP_NAME=chart_name,
        ),
        containers=[container_name],
        container_host_path_volumes={container_name: target_volumes},
        persistence_volumes=persistent_volumes,
        use_resource_limits=use_resource_limits,
        service_account_name=service_account_name,
    )
