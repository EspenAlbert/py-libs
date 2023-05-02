from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Union

from compose_chart_export.ports import PrefixPort
from model_lib.serialize.yaml_serialize import edit_helm_template, edit_yaml

service_yaml = "templates/service.yaml"
values_yaml = "values.yaml"


def update_values(
    chart_dir: Path,
    env_vars: dict[str, str],
    container_name: str,
    set_image: str = "",
):
    with edit_yaml(chart_dir / values_yaml) as all_values:
        values = all_values.setdefault(container_name.replace("-", "_"), {})
        old_image = values.get("image")
        values.clear()
        values.update(
            {
                key.replace("-", "_").replace(".", "_"): value
                for key, value in env_vars.items()
            }
        )
        if old_image:
            values["image"] = old_image
        if set_image:
            values["image"] = set_image


def add_container(
    chart_dir: Path,
    container_name: str,
    rel_path: str,
    use_resource_limits: bool = False,
):
    container_name_underscore = container_name.replace("-", "_")
    path = chart_dir / rel_path
    container_path = "spec.template.spec.containers"
    with edit_helm_template(path, yaml_path=container_path) as containers:
        assert isinstance(containers, list)
        container_spec = dict(
            name=container_name,
            image="{{ .Values.%s.image | quote }}" % container_name_underscore,
            imagePullPolicy="IfNotPresent",
            resources="{{- toYaml .Values.resources | nindent 10 }}"
            if use_resource_limits
            else {},
            command=[],
            env=[],
        )
        containers.append(container_spec)


def update_containers(
    chart_dir: Path,
    env_vars: Mapping[str, str],
    ports: Iterable[PrefixPort],
    container_name: str,
    command: Optional[Iterable[str]],
    rel_path: str,
    env_vars_field_refs: Mapping[str, str],
):
    container_name = container_name.replace("_", "-")
    path = chart_dir / rel_path
    if not path.exists():
        raise Exception(f"No {rel_path} file in chart: {chart_dir}")
    container_path = "spec.template.spec.containers"
    with edit_helm_template(path, yaml_path=container_path) as containers:
        assert isinstance(containers, list)
        relevant_container = [
            container for container in containers if container_name == container["name"]
        ]
        if not relevant_container:
            raise Exception(f"unable to find {container_name} in {path}")
        assert len(relevant_container) == 1
        container = relevant_container[0]
        assert isinstance(container, dict)
        env = container.setdefault("env", [])
        assert isinstance(env, list)
        env.clear()
        container_name_underscore = container_name.replace("-", "_")
        for name, value in env_vars.items():
            if field_ref := env_vars_field_refs.get(name):
                env.append(
                    dict(name=name, valueFrom=dict(fieldRef=dict(fieldPath=field_ref)))
                )
                continue
            value_template = "{{ .Values.%s.%s | quote }}" % (
                container_name_underscore,
                name.replace("-", "_").replace(".", "_"),
            )
            env.append(dict(name=name, value=value_template))
        container_ports = container["ports"] = []
        container_ports.extend(
            port_name(port, container_name, port_number_key="containerPort")
            for port in ports
        )

        if command:
            container["command"] = list(command)


def port_name(
    port_prefix: PrefixPort, container_name: str, port_number_key: str
) -> Dict[str, Union[int, str]]:
    kub_port_name = port_prefix.as_kub_port_name(port_prefix)
    if kub_port_name.endswith("root"):
        # ensure unique name when /root is used
        kub_port_name = PrefixPort.as_kub_port_name_raw(
            port_prefix.protocol, container_name
        )
    return {port_number_key: port_prefix.port, "name": kub_port_name}


def update_services(chart_dir: Path, ports: Iterable[PrefixPort], container_name: str):
    service_path = chart_dir / service_yaml
    if not service_path.exists():
        raise Exception(f"No service yaml found in chart: {chart_dir}")
    with edit_helm_template(service_path, yaml_path="spec.ports") as svc_ports:
        assert isinstance(svc_ports, list)
        not_found: Dict[int, PrefixPort] = {port.port: port for port in ports}
        for i, port_dict in enumerate(deepcopy(svc_ports)):
            port_number: int = port_dict.get("port")
            new: PrefixPort = not_found.pop(port_number, None)
            if new:
                svc_ports[i] = port_name(new, container_name, "port")
        for port_prefix in not_found.values():
            svc_ports.append(port_name(port_prefix, container_name, "port"))
