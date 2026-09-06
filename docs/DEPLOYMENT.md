# Deployment

## Recommended default

Use `deploy/kubernetes` or the default Helm values. This mode does not mount a Kubernetes API token and creates no ClusterRole.

## Live cluster metadata mode

Use `deploy/kubernetes/live-cluster` or `liveCluster.enabled=true` in Helm only when scheduling against live cluster facts is required. Protect the API with `KUBEFLIGHT_API_TOKEN`; the included live RBAC is read-only and intentionally excludes Secrets, logs, exec and writes.

## Exposure

KubeFlight can receive proprietary manifests and environment values. Do not expose an unauthenticated instance to the public internet. Put it behind your existing ingress authentication/SSO or use the built-in bearer token.

## Pod Security

The raw namespace labels enforce Restricted v1.37. The shipped Pod runs as UID 10001, non-root, read-only root filesystem, RuntimeDefault seccomp, no privilege escalation, and drops all Linux capabilities.
