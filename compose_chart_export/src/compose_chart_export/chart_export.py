import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional

from compose_chart_export.chart_file_templates import (
    ChartTemplateSpec,
    chart_yaml,
    daemonset_yaml,
    deployment_yaml,
    helm_ignore,
    helpers_tpl,
    notes_txt,
    persistence_volume_claims,
    service_account,
    service_yaml,
    values_yaml,
)
from zero_3rdparty.file_utils import clean_dir, ensure_parents_write_text

logger = logging.getLogger(__name__)


service_path = "templates/service.yaml"
daemonset_path = "templates/daemonset.yaml"
deployment_path = "templates/deployment.yaml"
PATH_TO_GENERATORS: Dict[str, Callable[[ChartTemplateSpec], str]] = {
    ".helmignore": helm_ignore,
    "Chart.yaml": chart_yaml,
    "values.yaml": values_yaml,
    "templates/_helpers.tpl": helpers_tpl,
    deployment_path: deployment_yaml,
    service_path: service_yaml,
    "templates/NOTES.txt": notes_txt,
    daemonset_path: daemonset_yaml,
    "templates/persistent-volume-claims.yaml": persistence_volume_claims,
    "templates/service_account.yaml": service_account,
}
SERVICE_DEPLOYMENT = "service_deployment"
DEPLOYMENT_ONLY = "deployment_only"
DAEMONSET = "daemonset"


def _export_chart(
    spec: ChartTemplateSpec,
    chart_path: Optional[Path] = None,
    skip_generators: Optional[List[str]] = None,
) -> Path:
    clean_dir(chart_path)
    skip_generators = skip_generators or []
    for rel_path, content_generator in PATH_TO_GENERATORS.items():
        if rel_path in skip_generators:
            continue
        dest = chart_path / rel_path
        if content := content_generator(spec):
            ensure_parents_write_text(dest, content)
    return chart_path


def export_service_deployment(
    spec: ChartTemplateSpec, chart_path: Optional[Path] = None
) -> Path:
    return _export_chart(spec, chart_path, skip_generators=[daemonset_path])


def export_deployment_only(
    spec: ChartTemplateSpec, chart_path: Optional[Path] = None
) -> Path:
    return _export_chart(
        spec, chart_path, skip_generators=[service_path, daemonset_path]
    )


def export_daemonset(
    spec: ChartTemplateSpec, chart_path: Optional[Path] = None
) -> Path:
    return _export_chart(
        spec, chart_path, skip_generators=[service_path, deployment_path]
    )


def export_chart(spec: ChartTemplateSpec, template_name: str, chart_path: Path) -> None:
    export = globals().get(f"export_{template_name}")
    assert export, f"unable to find export for {template_name}"
    export(spec, chart_path)
