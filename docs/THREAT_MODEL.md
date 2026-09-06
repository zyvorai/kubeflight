# Threat model

## Assets
- Kubernetes manifests and configuration values submitted for analysis
- optional cluster topology/capacity metadata
- optional live-cluster service-account token
- optional KubeFlight API bearer token

## Defaults
- live cluster reads disabled
- service-account token not mounted
- no Secret permissions
- no write permissions
- request body limited
- concurrent checks bounded
- per-client request rate bounded
- bearer token comparison uses constant-time comparison

## Non-goals
KubeFlight is not a secrets manager, WAF, CNI enforcement engine, admission controller, or replacement for Kubernetes authorization. Never submit real Secret payloads to an untrusted KubeFlight instance.
