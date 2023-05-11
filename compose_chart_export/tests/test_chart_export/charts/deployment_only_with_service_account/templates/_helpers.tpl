
{{/*

Templates from
https://github.com/bitnami/charts/tree/master/bitnami/common/#installing-the-chart
*/}}
{{- define "chart-label" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "common.labels.standard" -}}
app.kubernetes.io/name: {{ default .Chart.Name .Values.app_kubernetes_io_name }}
app.kubernetes.io/instance: {{ default .Release.Name .Values.app_kubernetes_io_instance }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Chart.AppVersion }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}


{{- end -}}

{{- define "common.labels.matchLabels" -}}
app.kubernetes.io/name: {{ default .Chart.Name .Values.app_kubernetes_io_name }}
app.kubernetes.io/instance: {{ default .Release.Name .Values.app_kubernetes_io_instance }}
{{- end -}}

# Template from
# https://github.com/influxdata/helm-charts/blob/master/charts/telegraf-ds/templates/_helpers.tpl#L400
{{- define "deployment_only_with_service_account.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
    {{ .Values.serviceAccount.name }}
{{- else -}}
    {{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}
