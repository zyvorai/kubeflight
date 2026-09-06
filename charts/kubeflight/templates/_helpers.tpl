{{- define "kubeflight.name" -}}kubeflight{{- end -}}
{{- define "kubeflight.fullname" -}}{{ .Release.Name }}{{- end -}}
{{- define "kubeflight.sa" -}}{{- if .Values.serviceAccount.name -}}{{ .Values.serviceAccount.name }}{{- else -}}{{ include "kubeflight.fullname" . }}{{- end -}}{{- end -}}
{{- define "kubeflight.labels" -}}
app.kubernetes.io/name: {{ include "kubeflight.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
