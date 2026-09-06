# Changelog

## 0.2.0 — 2026-09-06

### Correctness
- Kubernetes quantity parsing now supports DecimalSI, BinarySI and scientific notation and rejects invalid quantities.
- Scheduler subtracts existing non-terminal Pod reservations and places every proposed replica.
- Correct app/init/native-sidecar request accounting plus RuntimeClass overhead, ephemeral storage and extended resources.
- Node selectors, taints/tolerations, required node affinity, required pod affinity/anti-affinity and hard topology spread simulation.
- Deletion-aware blast radius combines baseline and proposed dependency graphs.
- Dependency discovery no longer scans image strings, preventing `redis:7.4.0`-style false edges.
- NetworkPolicy analysis covers both ingress and egress with selectors and ports.
- Rich RBAC permission contracts support API groups, verbs and resourceNames.

### Security
- Expanded Restricted Pod Security checks including Windows HostProcess, explicit UID 0, SELinux/AppArmor, sysctls, probe/lifecycle hosts and ephemeral containers.
- Default Kubernetes deployment no longer mounts a service-account token or grants cluster-wide RBAC.
- Live cluster mode is explicit, read-only and requires bearer authentication.
- API body, concurrency and per-client rate guards added.

### Developer experience
- `kubeflight plan` auto-detects common deployment roots and Helm/Kustomize renderers.
- Markdown and SARIF reports added.
- GitHub Action emits JSON, SARIF and a step summary.
- CI includes Helm/Kustomize validation, container build and kind E2E.
- Release workflow includes standalone binaries, multi-arch images, SBOM and provenance wiring.

## 0.1.0
- Initial public prototype.
