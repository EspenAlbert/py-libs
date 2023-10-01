from __future__ import annotations

import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Iterable, Optional, cast

import semver  # type: ignore
from pydantic import BaseModel

from compose_chart_export.chart_combiner import combine
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
    secret_with_env_vars,
    update_containers,
    update_services,
    update_values,
)
from compose_chart_export.chart_read import container_template
from compose_chart_export.ports import PortProtocol, PrefixPort
from compose_chart_export.settings import ChartTemplate
from docker_compose_parser.file_models import (
    ComposeHealthCheck,
    ComposeServiceInfo,
    iter_compose_info,
    read_compose_info,
)
from model_lib import FileFormat, parse_model, parse_payload
from model_lib.serialize.yaml_serialize import edit_yaml
from zero_3rdparty.file_utils import PathLike, copy
from zero_3rdparty.str_utils import want_bool, words_to_list

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


def parse_chart_name(labels: dict[str, str]) -> str:
    return labels.get("chart_name", "")


def parse_extra_ports(labels: dict[str, str]) -> list[str]:
    return [p for p in labels.get("PORTS_EXTRA", "").strip().split(",") if p.isdigit()]


def parse_secret_env_vars(
    labels: dict[str, str]
) -> tuple[dict[str, list[str]], set[str]]:
    all_secret_env_vars: set[str] = set()
    secret_env_vars: dict[str, list[str]] = {}
    for name, raw_env_vars in labels.items():
        if not name.startswith("secret_"):
            continue
        secret_name = name.removeprefix("secret_").replace("-", "_")
        env_vars = words_to_list(raw_env_vars, " ", ",")
        all_secret_env_vars.update(env_vars)
        secret_env_vars[secret_name] = env_vars
    return secret_env_vars, all_secret_env_vars


def parse_healthcheck_probes(labels: dict[str, str]) -> list[str]:
    """
    >>> parse_healthcheck_probes({})
    []
    >>> parse_healthcheck_probes({"healthcheck_probes": "readiness"})
    ['readiness']
    >>> parse_healthcheck_probes({"healthcheck_probes": "readiness liveness"})
    ['readiness', 'liveness']
    >>> parse_healthcheck_probes({"healthcheck_probes": "readiness, liveness"})
    ['readiness', 'liveness']
    """
    raw_probes = words_to_list(labels.get("healthcheck_probes", ""), " ", ",")
    probes = [probe.removesuffix("Probe") for probe in raw_probes]
    valid_probes = {"readiness", "liveness", "startup"}
    invalid_probes = [p for p in probes if p not in valid_probes]
    assert not invalid_probes, f"invalid probes specified: {invalid_probes}"
    return probes


class ExtraContainer(BaseModel):
    name: kubernetes_label_regex
    env: dict[str, str]
    command: list[str]


def parse_service_name_extra_containers(
    compose_path: Path, chart_name: str
) -> tuple[str, list[ExtraContainer]]:
    extra_containers = []
    service_names = []
    chart_name_service_name = {}
    for each_service_name, info in iter_compose_info(compose_path):
        if info.labels.get("extra_container") == "true":
            container_name = each_service_name.replace("_", "-")
            extra_containers.append(
                ExtraContainer(
                    name=container_name, env=info.default_env, command=info.command
                )
            )
        elif service_chart_name := parse_chart_name(info.labels):
            chart_name_service_name[service_chart_name] = each_service_name
        else:
            service_names.append(each_service_name)
    if chart_name and chart_name_service_name:
        found_service = chart_name_service_name.get(chart_name)
        if not found_service:
            raise ValueError(f"chart name: {chart_name} not found in {compose_path}")
        return found_service, extra_containers
    if chart_name_service_name:
        service_names = list(chart_name_service_name.values())
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
        semver.VersionInfo.parse(check_version)
        return chart_version
    except ValueError:
        updated_version = f"0.0.1-{chart_version}"
        logger.warning(
            f"not a valid semver: {chart_version}, will try: {updated_version}"
        )
    semver.VersionInfo.parse(updated_version)
    return updated_version


def probe_values(healthcheck: ComposeHealthCheck) -> dict:
    # https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/#define-readiness-probes
    return dict(
        exec=dict(command=healthcheck.command_list_k8s),
        initialDelaySeconds=healthcheck.start_period_seconds,
        periodSeconds=healthcheck.interval_seconds,
        timeoutSeconds=healthcheck.timeout_seconds,
        failureThreshold=healthcheck.retries,
    )


def export_from_compose(  # noqa: C901
    compose_path: PathLike,
    chart_version: str,
    chart_name: str = "",
    image_url: str = "unset",
    on_exported: Callable[[Path], None] | None = None,
    use_chart_name_as_container_name: bool = True,
    old_chart_path: Optional[Path] = None,
):
    chart_version = ensure_chart_version_valid(chart_version)
    compose_path = Path(compose_path)
    service_name, extra_containers = parse_service_name_extra_containers(
        compose_path, chart_name
    )
    info = read_compose_info(compose_path, service_name)
    env = info.default_env
    compose_labels = info.labels
    chart_name = chart_name or parse_chart_name(compose_labels)
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
                chart_name,
                container_name,
                chart_version,
                service_name,
                info,
                prefix_ports,
            )
            export_chart(spec, template_name, chart_path)
        probes: dict[str, dict] = {}
        if healthcheck := info.healthcheck:
            for probe in parse_healthcheck_probes(compose_labels):
                probes[f"{probe}Probe"] = probe_values(healthcheck)
        secret_env_vars, all_secret_env_vars = parse_secret_env_vars(compose_labels)
        secret_names = list(secret_env_vars)
        update_values(
            chart_path,
            env,
            container_name=container_name,
            set_image=image_url,
            probe_values=probes,
            secret_names=secret_names,
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
            readiness_enabled="readinessProbe" in probes,
            liveness_enabled="livenessProbe" in probes,
            startup_enabled="startupProbe" in probes,
            secret_names=secret_names,
            all_secret_env_vars=all_secret_env_vars,
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
                    readiness_enabled=False,
                    liveness_enabled=False,
                    startup_enabled=False,
                    secret_names=[],
                    all_secret_env_vars=set(),
                )
                update_values(
                    chart_path,
                    container.env,
                    container_name=container.name,
                    set_image="unset",
                )
        for secret_name, env_vars in secret_env_vars.items():
            filename = f"secret_{secret_name}.yaml"
            secret_content = secret_with_env_vars(container_name, secret_name, env_vars)
            (chart_path / "templates" / filename).write_text(secret_content)

        if old_chart_path:
            combine(old_chart_path, chart_path)
        if on_exported:
            on_exported(chart_path)


def parse_container_ports(
    compose_labels: dict[str, str], ports: Iterable[tuple[int, int]]
) -> list[PrefixPort]:
    prefix_ports = []
    if extra_ports := parse_extra_ports(compose_labels):
        ports = list(ports) + [(int(p), int(p)) for p in extra_ports]
    for _, container_port in ports:
        port_protocol = compose_labels.get(
            f"PORT_PROTOCOL_{container_port}", PortProtocol.http
        )
        prefix_port = PrefixPort(
            prefix="/", port=container_port, protocol=port_protocol
        )
        if prefix_port not in prefix_ports:
            prefix_ports.append(prefix_port)
    return prefix_ports


def create_spec(
    chart_name: str,
    container_name: str,
    chart_version: str,
    service_name: str,
    info: ComposeServiceInfo,
    prefix_ports: list[PrefixPort],
) -> tuple[str, ChartTemplateSpec]:
    compose_labels = info.labels
    if name := parse_template_name(compose_labels):
        template_name = cast(ChartTemplate, name)
    elif prefix_ports:
        template_name = ChartTemplate.SERVICE_DEPLOYMENT
    else:
        template_name = ChartTemplate.DEPLOYMENT_ONLY
    logger.info(f"using template name: {template_name} for {service_name}")
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
