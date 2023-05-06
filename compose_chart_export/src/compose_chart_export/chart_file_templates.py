# flake8: noqa
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, List, Tuple

from model_lib.serialize.yaml_serialize import edit_helm_template
from pydantic import Field, constr, validator
from zero_3rdparty.enum_utils import StrEnum

from model_lib import Event


class ReplaceStr(StrEnum):
    APP_NAME = "APP_NAME"
    APP_VERSION = "APP_VERSION"
    CHART_VERSION = "CHART_VERSION"
    REPO_NAME = "REPO_NAME"
    REPO_OWNER = "REPO_OWNER"


_CHART_YAML = f"""apiVersion: v2
name: {ReplaceStr.APP_NAME}
description: A Helm chart for {ReplaceStr.APP_NAME}

type: application
version: {ReplaceStr.CHART_VERSION}
appVersion: {ReplaceStr.APP_VERSION}
"""


# start with number or character ". -_" allowed, + and / not allowed
# https://atomist.github.io/sdm-pack-k8s/modules/_lib_kubernetes_labels_.html
kubernetes_label_regex = constr(
    regex=r"^([a-zA-Z0-9][-a-zA-Z0-9_\.]*[a-zA-Z0-9])?$", max_length=63
)
dns_safe = constr(regex=r"^[a-z-]+$")


class TemplateReplacements(Event):
    """
    >>> TemplateReplacements(REPO_NAME="py-hooks", REPO_OWNER="wheelme-devops", CHART_VERSION="0.0.1")
    TemplateReplacements(APP_VERSION='', CHART_VERSION='0.0.1', REPO_NAME='py-hooks', REPO_OWNER='wheelme-devops', APP_NAME='py-hooks')
    >>> TemplateReplacements(REPO_NAME="py-hooks._ok", REPO_OWNER="wheelme-devops", CHART_VERSION="0.0.1")
    TemplateReplacements(APP_VERSION='', CHART_VERSION='0.0.1', REPO_NAME='py-hooks._ok', REPO_OWNER='wheelme-devops', APP_NAME='py-hooks._ok')
    >>> TemplateReplacements(REPO_NAME="py+hooks", REPO_OWNER="wheelme-devops", CHART_VERSION="0.0.1")
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError: 1 validation error for TemplateReplacements
    REPO_NAME
      string does not match regex "^([a-zA-Z0-9][-a-zA-Z0-9_\.]*[a-zA-Z0-9])?$" (type=value_error.str.regex; pattern=^([a-zA-Z0-9][-a-zA-Z0-9_\.]*[a-zA-Z0-9])?$)

    >>> TemplateReplacements(REPO_NAME="py-hooks/", REPO_OWNER="wheelme-devops", CHART_VERSION="0.0.1")
    Traceback (most recent call last):
    pydantic.error_wrappers.ValidationError: 1 validation error for TemplateReplacements
    REPO_NAME
      string does not match regex "^([a-zA-Z0-9][-a-zA-Z0-9_\.]*[a-zA-Z0-9])?$" (type=value_error.str.regex; pattern=^([a-zA-Z0-9][-a-zA-Z0-9_\.]*[a-zA-Z0-9])?$)
    """

    class Config:
        allow_mutation = True

    CHART_VERSION: kubernetes_label_regex
    APP_NAME: kubernetes_label_regex
    APP_VERSION: kubernetes_label_regex = ""
    REPO_NAME: kubernetes_label_regex = ""
    REPO_OWNER: kubernetes_label_regex = ""

    def replace(self, string: str) -> str:
        for key, value in self.dict().items():
            assert not (key in string and value == ""), f"missing key={key}"
            string = string.replace(key, value)

        return string


class HostPathContainerPath(Event):
    """
    >>> HostPathContainerPath(name="last_ts_path", host_path="/some_host_path")
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError: 1 validation error for HostPathContainerPath
    name
      string does not match regex "^[a-z-]+$" (type=value_error.str.regex; pattern=^[a-z-]+$)
    >>> HostPathContainerPath(name="last-ts-path", host_path="/some_host_path")
    HostPathContainerPath(name='last-ts-path', host_path='/some_host_path', container_path='/some_host_path')
    """

    name: dns_safe
    host_path: str
    container_path: str = ""

    @validator("container_path", always=True)
    def use_host_path_if_empty(cls, value: str, values: dict):
        if not value:
            return values["host_path"]
        return value


class PersistentVolume(Event):
    name: str
    container_path: str
    storage_gb: int

    @property
    def name_var(self) -> str:
        return '{{ printf "%s-%s" .Release.Name "PVC_NAME" }}'.replace(
            "PVC_NAME", self.name
        )


docker_socket = HostPathContainerPath(
    name="docker-socket", host_path="/var/run/docker.sock"
)


class ChartTemplateSpec(Event):
    replacements: TemplateReplacements
    containers: List[str]
    container_host_path_volumes: Dict[str, List[HostPathContainerPath]] = Field(
        default_factory=dict
    )
    persistence_volumes: list[PersistentVolume] = Field(default_factory=list)
    use_resource_limits: bool = True
    service_account_name: str = ""
    extra_labels: dict[str, kubernetes_label_regex] = Field(default_factory=dict)

    @property
    def use_service_account(self) -> bool:
        return bool(self.service_account_name)

    @property
    def containers_values_names(self) -> List[str]:
        return [name.replace("-", "_") for name in self.containers]

    @property
    def container_name_value_name(self) -> List[Tuple[str, str]]:
        return list(zip(self.containers, self.containers_values_names))


def chart_yaml(spec: ChartTemplateSpec) -> str:
    return spec.replacements.replace(_CHART_YAML)


_VALUES_YAML = """podLabels: {}
podAnnotations: {}
nodeSelector: {}
replicas: 1"""

_RESOURCES_YAML = """\
resources:
  limits:
    cpu: 500m
    memory: 512Mi"""

_SERVICE_ACCOUNT_VALUES = """\
serviceAccount:
  name: SERVICE_ACCOUNT_NAME
  annotations: {}
  create: true
"""


def values_yaml(spec: ChartTemplateSpec) -> str:
    values_base = _VALUES_YAML
    if spec.use_resource_limits:
        values_base += f"\n{_RESOURCES_YAML}"
    if service_account_name := spec.service_account_name:
        service_account_values = _SERVICE_ACCOUNT_VALUES.replace(
            "SERVICE_ACCOUNT_NAME", service_account_name
        )
        values_base += f"\n{service_account_values}"
    return values_base + "".join(
        f"\n{name}: \n  image: override_me" for name in spec.containers_values_names
    )


_helm_ignore = """# Patterns to ignore when building packages.
# This supports shell glob matching, relative path matching, and
# negation (prefixed with !). Only one pattern per line.
.DS_Store
# Common VCS dirs
.git/
.gitignore
.bzr/
.bzrignore
.hg/
.hgignore
.svn/
# Common backup files
*.swp
*.bak
*.tmp
*~
# Various IDEs
.project
.idea/
*.tmproj
.vscode/
"""


def helm_ignore(spec: ChartTemplateSpec) -> str:
    return _helm_ignore


_HELPERS_TPL = """
{{/*

Templates from
https://github.com/bitnami/charts/tree/master/bitnami/common/#installing-the-chart
*/}}
{{- define "chart-label" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "common.labels.standard" -}}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
EXTRA_LABELS
{{- end -}}

{{- define "common.labels.matchLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
"""
_service_account_tpl = """
# Template from
# https://github.com/influxdata/helm-charts/blob/master/charts/telegraf-ds/templates/_helpers.tpl#L400
{{- define "APP_NAME.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
    {{ .Values.serviceAccount.name }}
{{- else -}}
    {{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}
"""


def helpers_tpl(spec: ChartTemplateSpec) -> str:
    helpers_tpl_content = spec.replacements.replace(_HELPERS_TPL)
    extra_labels_str = "\n"
    if extra_labels := spec.extra_labels:
        extra_labels_str = "\n".join(
            f"{key}: {value}" for key, value in extra_labels.items()
        )
    if spec.use_service_account:
        helpers_tpl_content += _service_account_tpl.replace(
            "APP_NAME", spec.replacements.APP_NAME
        )
    helpers_tpl_content = helpers_tpl_content.replace("EXTRA_LABELS", extra_labels_str)
    return helpers_tpl_content


_DEPLOYMENT_YAML = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Release.Name }}
  namespace: {{ .Release.Namespace }}
  labels:
  {{- include "common.labels.standard" . | nindent 4 }}
spec:
  replicas: {{ .Values.replicas }}
  selector:
    matchLabels:
    {{- include "common.labels.matchLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
      {{- include "common.labels.standard" . | nindent 8 }}
      {{- with .Values.podLabels }}
      {{- toYaml . | nindent 8 }}
      {{- end }}
      annotations:
      {{- with .Values.podAnnotations }}
      {{- toYaml . | nindent 8 }}
      {{- end }}
    spec:
      containers: []"""

_NODE_SELECTOR_OPTIONAL = """      nodeSelector:
      {{- with .Values.nodeSelector }}
      {{- toYaml . | nindent 8 }}
      {{- end }}
"""


def deployment_yaml(spec: ChartTemplateSpec) -> str:
    """
    spec:
      nodeSelector:
        group: NODE_SELECTOR_GROUP
    """
    raw = _DEPLOYMENT_YAML
    return _add_template_spec(raw, spec)


def _add_template_spec(template: str, spec: ChartTemplateSpec):
    with TemporaryDirectory() as path:
        deploy_file = Path(path) / "template.yaml"
        deploy_file.write_text(template)
        with edit_helm_template(
            deploy_file, yaml_path="spec.template.spec"
        ) as file_spec:  # type: dict
            if spec.use_service_account:
                file_spec[
                    "serviceAccountName"
                ] = '{{ template "APP_NAME.serviceAccountName" . }}'.replace(
                    "APP_NAME", spec.replacements.APP_NAME
                )
            containers: list = file_spec["containers"]
            for name, value_name in spec.container_name_value_name:
                container_spec = dict(
                    name=name,
                    image="{{ .Values.%s.image | quote }}" % value_name,
                    imagePullPolicy="IfNotPresent",
                    resources="{{- toYaml .Values.resources | nindent 10 }}"
                    if spec.use_resource_limits
                    else {},
                    ports=[],  # override by artifacts plugin
                    # command=[],  # override by artifacts plugin
                    env=[],  # override by artifacts plugin
                )
                volume_mounts: list = container_spec.setdefault("volumeMounts", [])
                if volumes := spec.container_host_path_volumes.get(name):
                    volume_mounts.extend(
                        dict(name=mount.name, mountPath=mount.container_path)
                        for mount in volumes
                    )
                if pv_volumes := spec.persistence_volumes:
                    volume_mounts.extend(
                        [
                            dict(name=pv.name, mountPath=pv.container_path)
                            for pv in pv_volumes
                        ]
                    )
                if not volume_mounts:
                    container_spec.pop("volumeMounts")

                containers.append(container_spec)
            spec_volumes: list = file_spec.setdefault("volumes", [])
            if volumes := spec.container_host_path_volumes.get(name):
                spec_volumes.extend(
                    dict(name=mount.name, hostPath=dict(path=mount.host_path))
                    for mount in volumes
                )
            if pv_volumes := spec.persistence_volumes:
                spec_volumes.extend(
                    dict(
                        name=pv.name, persistentVolumeClaim=dict(claimName=pv.name_var)
                    )
                    for pv in pv_volumes
                )
            if not spec_volumes:
                file_spec.pop("volumes")
        return "\n".join([deploy_file.read_text(), _NODE_SELECTOR_OPTIONAL])


_DAEMONSET_YAML = """\
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: {{ .Release.Name }}
  namespace: {{ .Release.Namespace }}
  labels:
  {{- include "common.labels.standard" . | nindent 4 }}
spec:
  selector:
    matchLabels:
    {{- include "common.labels.matchLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
      {{- include "common.labels.standard" . | nindent 8 }}
      {{- with .Values.podLabels }}
      {{- toYaml . | nindent 8 }}
      {{- end }}
      annotations:
      {{- with .Values.podAnnotations }}
      {{- toYaml . | nindent 8 }}
      {{- end }}
    spec:
      containers: []
"""


def daemonset_yaml(spec: ChartTemplateSpec) -> str:
    return _add_template_spec(_DAEMONSET_YAML, spec)


_SERVICE_YAML = """apiVersion: v1
kind: Service
metadata:
  name: {{ .Release.Name }}
  namespace: {{ .Release.Namespace }}
  labels:
  {{- include "common.labels.standard" . | nindent 4 }}
spec:
  type: ClusterIP
  ports: []
  selector:
  {{- include "common.labels.matchLabels" . | nindent 4 }}
"""


def service_yaml(spec: ChartTemplateSpec):
    return _SERVICE_YAML


_NOTES_TXT = """REVISION={{ .Release.Revision }}
# Tags
{{ include "common.labels.standard" .}}
"""


def notes_txt(spec: ChartTemplateSpec):
    return _NOTES_TXT


_PVC_YAML = """apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: PVC_NAME
  namespace: {{ .Release.Namespace }}
  labels:
  {{- include "common.labels.standard" . | nindent 4 }}
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: PVC_SIZEGi
"""
#   storageClassName: gp2 leaving storageClasName empty will choose a default provider


def persistence_volume_claims(spec: ChartTemplateSpec) -> str:
    return "---".join(
        _PVC_YAML.replace("PVC_NAME", pv.name_var).replace(
            "PVC_SIZE", str(pv.storage_gb)
        )
        for pv in spec.persistence_volumes
    )


_SERVICE_ACCOUNT = """\
{{- if .Values.serviceAccount.create }}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ .Values.serviceAccount.name }}
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "common.labels.standard" . | nindent 4 }}
  {{- with .Values.serviceAccount.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
{{- end }}
"""


def service_account(spec: ChartTemplateSpec) -> str:
    if spec.use_service_account:
        return _SERVICE_ACCOUNT
    return ""
