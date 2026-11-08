{{/* Chart name, truncated to 63 chars (DNS label limit). */}}
{{- define "trato.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "trato.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/* Usage: include "trato.selectorLabels" (dict "root" $ "component" "web") */}}
{{- define "trato.selectorLabels" -}}
app.kubernetes.io/name: {{ include "trato.name" .root }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{- define "trato.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .root.Chart.Name .root.Chart.Version | replace "+" "_" }}
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
app.kubernetes.io/part-of: trato
app.kubernetes.io/version: {{ .root.Chart.AppVersion | quote }}
{{ include "trato.selectorLabels" . }}
{{- end }}

{{/* Resource name for one component: <fullname>-<component>. Usage: include "trato.componentName" (dict "root" $ "component" "web") */}}
{{- define "trato.componentName" -}}
{{- printf "%s-%s" (include "trato.fullname" .root) .component | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Image reference. Usage: include "trato.image" (dict "root" $ "image" .Values.web.image) */}}
{{- define "trato.image" -}}
{{- printf "%s:%s" .image.repository (.image.tag | default .root.Chart.AppVersion) }}
{{- end }}

{{/* Pod-level hardening shared by every component (non-root, no privilege escalation path). */}}
{{- define "trato.podSecurityContext" -}}
runAsNonRoot: true
runAsUser: 10001
runAsGroup: 10001
fsGroup: 10001
seccompProfile:
  type: RuntimeDefault
{{- end }}

{{- define "trato.containerSecurityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop:
    - ALL
{{- end }}

{{/* Non-secret env from the shared ConfigMap, plus the component's secret. */}}
{{- define "trato.envFrom" -}}
- configMapRef:
    name: {{ include "trato.fullname" .root }}-config
- secretRef:
    name: {{ .secretName }}
{{- end }}

{{/* Usage: include "trato.serviceAccountName" (dict "root" $ "component" "web" "sa" .Values.web.serviceAccount) */}}
{{- define "trato.serviceAccountName" -}}
{{- if .sa.create }}
{{- default (include "trato.componentName" .) .sa.name }}
{{- else }}
{{- default "default" .sa.name }}
{{- end }}
{{- end }}
