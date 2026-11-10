{{/* Chart name, truncated to 63 chars (DNS label limit). */}}
{{- define "apex.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "apex.fullname" -}}
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

{{/* Usage: include "apex.selectorLabels" (dict "root" $ "component" "web") */}}
{{- define "apex.selectorLabels" -}}
app.kubernetes.io/name: {{ include "apex.name" .root }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{- define "apex.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .root.Chart.Name .root.Chart.Version | replace "+" "_" }}
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
app.kubernetes.io/part-of: apex
app.kubernetes.io/version: {{ .root.Chart.AppVersion | quote }}
{{ include "apex.selectorLabels" . }}
{{- end }}

{{/* Resource name for one component: <fullname>-<component>. Usage: include "apex.componentName" (dict "root" $ "component" "web") */}}
{{- define "apex.componentName" -}}
{{- printf "%s-%s" (include "apex.fullname" .root) .component | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Image reference. Usage: include "apex.image" (dict "root" $ "image" .Values.web.image) */}}
{{- define "apex.image" -}}
{{- printf "%s:%s" .image.repository (.image.tag | default .root.Chart.AppVersion) }}
{{- end }}

{{/* Pod-level hardening shared by every component (non-root, no privilege escalation path). */}}
{{- define "apex.podSecurityContext" -}}
runAsNonRoot: true
runAsUser: 10001
runAsGroup: 10001
fsGroup: 10001
seccompProfile:
  type: RuntimeDefault
{{- end }}

{{- define "apex.containerSecurityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop:
    - ALL
{{- end }}

{{/* Non-secret env from the shared ConfigMap, plus the component's secret. */}}
{{- define "apex.envFrom" -}}
- configMapRef:
    name: {{ include "apex.fullname" .root }}-config
- secretRef:
    name: {{ .secretName }}
{{- end }}

{{/* Usage: include "apex.serviceAccountName" (dict "root" $ "component" "web" "sa" .Values.web.serviceAccount) */}}
{{- define "apex.serviceAccountName" -}}
{{- if .sa.create }}
{{- default (include "apex.componentName" .) .sa.name }}
{{- else }}
{{- default "default" .sa.name }}
{{- end }}
{{- end }}
