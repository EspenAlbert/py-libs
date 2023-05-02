from __future__ import annotations

from pathlib import Path
from typing import Any

from model_lib.serialize.yaml_serialize import edit_helm_template, edit_yaml

from model_lib import parse_payload


def target_name_underscore(name: str) -> str:
    """Necessary in helm_charts values.yaml files as '-' is not valid in go
    templates."""
    return name.replace("-", "_")


def container_template(chart_path: Path) -> str:
    env_template_file = ["deployment.yaml", "daemonset.yaml"]
    rel_path = ""
    for filename in env_template_file:
        rel_path = f"templates/{filename}"
        if (chart_path / rel_path).exists():
            break
    assert rel_path, f"no env_template_file found in {chart_path}/templates"
    return rel_path


def read_chart_version(path: Path):
    return parse_payload(path / "Chart.yaml")["version"]


def read_app_version(path: Path):
    return parse_payload(path / "Chart.yaml")["appVersion"]


def set_chart_version(chart: Path, version: str, app_version: str = ""):
    with edit_yaml(chart / "Chart.yaml") as chart_yaml:
        chart_yaml["version"] = version
        if app_version:
            chart_yaml["appVersion"] = app_version


def chart_has_no_changes(chart_path: Path, online_chart_path: Path) -> bool:
    template_rel_path = container_template(chart_path)
    new = (chart_path / template_rel_path).read_text().strip()
    old = (online_chart_path / template_rel_path).read_text().strip()
    return old == new


def read_values(chart_path: Path) -> dict[str, Any]:
    return parse_payload(chart_path / "values.yaml")


def read_env_vars(chart_path: Path, target_name: str) -> dict[str, str]:
    chart_values = read_values(chart_path)
    key = target_name_underscore(target_name)
    return chart_values[key]


def read_container_name(chart_path: Path) -> str:
    template = container_template(chart_path)
    path = chart_path / template
    container_path = "spec.template.spec.containers"
    names = []
    with edit_helm_template(path, yaml_path=container_path) as containers:
        for container in containers:
            names.append(container["name"])
    assert len(names) == 1, f"more than 1 container: {path}"
    return names[0]
