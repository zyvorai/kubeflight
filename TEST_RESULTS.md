# KubeFlight v0.2.0 — Test Results

Release validation performed on 2026-09-06.

## Locally executed and passed

- Python compile check: PASS
- Unit/API/CLI/regression suite: **35/35 PASS**
- API + embedded dashboard smoke: PASS
- Demo preflight: **84/100 — REVIEW REQUIRED**
- Raw Kubernetes self-analysis: **100/100 — SAFE TO DEPLOY, 0 high/critical findings**
- `action.yml`, Helm metadata/values and GitHub workflow YAML parsing: PASS
- Python wheel build: PASS (`kubeflight-0.2.0-py3-none-any.whl`)
- Wheel contains embedded dashboard and demo assets: PASS
- Installed-wheel CLI manifest analysis: PASS
- SARIF JSON generation/parsing: PASS (covered by tests)
- Markdown report generation: PASS (covered by tests)
- Live-cluster-disabled and bearer-auth API behavior: PASS (covered by tests)

## Regression coverage added in v0.2

- scientific/BinarySI Kubernetes quantities
- invalid quantity fail-closed behavior
- existing Pod reservation subtraction
- every-replica scheduling
- regular init vs application request accounting
- native sidecar init accounting
- RuntimeClass overhead
- required node affinity
- required pod anti-affinity
- hard topology spread
- deletion-aware blast radius
- image-name dependency false-positive regression
- egress NetworkPolicy blocking
- rich RBAC contracts
- Windows HostProcess
- explicit UID 0

## CI-only validation wired into GitHub Actions

The current local execution environment does not provide Docker, Helm, kubectl, kind, Kustomize, or PyInstaller binaries. Therefore the following are configured in GitHub Actions but are **not claimed as locally executed**:

- `helm lint` / `helm template`
- `kubectl kustomize`
- Docker image build
- kind cluster end-to-end deployment
- PyInstaller standalone binaries on Linux/macOS/Windows
- multi-architecture image publishing
- SBOM/provenance release actions

The exact release ZIP is additionally extracted into a fresh directory and the local release checks are rerun before delivery.
