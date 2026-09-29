# KubeFlight

[![CI](https://github.com/zyvorai/kubeflight/actions/workflows/ci.yml/badge.svg)](https://github.com/zyvorai/kubeflight/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-0071e3?style=flat-square&labelColor=1d1d1f)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.2.0-informational)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

![KubeFlight — Kubernetes preflight simulator](docs/social/kubeflight-share-card.png)

**Know what may break before you deploy.**

> KubeFlight is intentionally deterministic. It does not use an LLM to decide whether a deployment is safe.

[**Docs site**](https://zyvorai.github.io/kubeflight/) · [**Is this for you?**](#is-this-for-you) · [**v0.2.0 capabilities**](#v020-capabilities) · [**Quick start**](#quick-start) · [**License**](#license)

KubeFlight is an Apache-2.0, local-first Kubernetes deployment simulator and preflight engine from Zyvor AI Labs. It analyzes rendered manifests, optionally compares them with a baseline and cluster snapshot, simulates placement, evaluates security/RBAC/network policy, estimates change cost, and returns an evidence-backed safety decision.

A valid manifest can still fail in production because of node capacity, existing Pods, taints, affinity, NetworkPolicy, missing RBAC, removed APIs, cost growth, availability constraints, or downstream dependencies. KubeFlight puts those signals into one repeatable preflight.

## Is this for you?

KubeFlight is a small, open-source (Apache-2.0), local-first, deterministic preflight simulator — it's not a cost-monitoring dashboard, not a general-purpose policy engine, and not an AI-assisted deployment advisor.

| | **KubeFlight** | Datree / Fairwinds Insights | Polaris / kube-score | OPA/Conftest, Kyverno | k8sgpt | `kubectl diff --dry-run=server` |
|---|---|---|---|---|---|---|
| Primary scope | Preflight simulation: placement, RBAC, NetworkPolicy, cost delta, evidence-backed decision | Policy/config scanning + fleet dashboard (some proprietary) | Static manifest best-practice linting | Generic policy-as-code enforcement | LLM-based cluster diagnosis | Server-side dry-run diff only, no scoring |
| Decision method | Deterministic — "does not use an LLM to decide whether a deployment is safe" | Deterministic rules | Deterministic rules | Deterministic rules you author | LLM-based (probabilistic) | N/A (raw diff) |
| Placement/scheduling simulation | Yes, against an offline or live cluster snapshot | No | No | No | No | No |
| Cost estimation | Yes (provider-neutral) | Some (Fairwinds/Kubecost-adjacent tools) | No | No | No | No |
| License | Apache-2.0 | Mixed open-core/proprietary | Apache-2.0 | Apache-2.0 | Apache-2.0 | N/A (built into kubectl) |

*(General characterizations as of writing — verify current features against each project's own docs.)*

**Maturity, stated honestly**: current version is 0.2.0 ([`CHANGELOG.md`](CHANGELOG.md)). KubeFlight is a **preflight simulator**, not a byte-for-byte implementation of kube-scheduler plugins, admission webhooks, CNI dataplanes, or production traffic. Unknown facts are reported conservatively rather than invented. For an authoritative check beyond simulation, it explicitly defers to `kubectl apply --dry-run=server` as an opt-in feature requiring a real cluster.

Release validation ([`TEST_RESULTS.md`](TEST_RESULTS.md)): 35/35 unit/API/CLI/regression tests pass, a demo preflight scores 84/100 (review required — the demo manifest is intentionally imperfect), and KubeFlight's own Kubernetes deployment self-analyzes at 100/100 with zero high/critical findings.

New here? [`docs/FAQ.md`](docs/FAQ.md) covers licensing, support, and production-readiness questions; [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) covers real operational issues with their documented fix.

## v0.2.0 capabilities

| Area | Checks |
| --- | --- |
| Parsing/rendering | multi-document YAML/JSON, Kubernetes `List`, Helm auto-render, Kustomize auto-render, repo path auto-detection |
| Schema baseline | object identity, structural checks, selector/template consistency, removed APIs; optional authoritative `kubectl --dry-run=server` |
| Quantities | Kubernetes-style DecimalSI/BinarySI/scientific quantities; invalid quantities fail closed instead of becoming zero |
| Restricted security | host namespaces, hostPath, privileged, capabilities, seccomp, non-root/UID 0, SELinux, AppArmor, Windows HostProcess, probe/lifecycle host fields |
| Scheduling | existing Pod reservations, every replica, app/init/native-sidecar accounting, RuntimeClass overhead, GPU/extended resources, taints/tolerations, required affinity/anti-affinity, hard topology spread |
| Reliability | requests/limits, readiness/liveness, PDB coverage, image pinning |
| Network | statically inferred Service dependencies, ingress + egress NetworkPolicy isolation |
| RBAC | ServiceAccount presence plus explicit API group/resource/subresource/verb/resourceName contracts via annotation |
| Change impact | baseline/proposed resource diff, dependency graphs, deletion-aware reverse blast radius |
| Cost | provider-neutral request/storage estimate and baseline delta |
| Reports | text, JSON, HTML, Markdown/PR summary, SARIF |
| API/UI | FastAPI REST API, OpenAPI docs, embedded dashboard, request-size/concurrency/rate guards, optional bearer auth |
| Kubernetes | hardened raw manifests, Kustomize, Helm, opt-in live-cluster RBAC, restricted Pod Security namespace |
| GitHub | composite Action, SARIF upload, Helm/Kustomize checks, container build, kind E2E, multi-arch release |

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .

kubeflight check examples/demo/app.yaml \
  --baseline examples/demo/baseline.yaml \
  --cluster-snapshot examples/demo/cluster-snapshot.json \
  --fail-on never
```

Or auto-detect a conventional Kubernetes/Helm/Kustomize path:

```bash
kubeflight plan
```

Reports: `kubeflight check <path> --format json|html|markdown|sarif --output <file>`. Optional authoritative validation: `kubeflight check <path> --server-dry-run` shells out to `kubectl apply --dry-run=server` against a configured cluster.

### Dashboard

```bash
kubeflight serve --host 0.0.0.0 --port 8080   # http://localhost:8080, API docs at /api/docs
```

The browser sends manifests only to the KubeFlight instance you opened — no external SaaS or AI call. Do not send Secrets to an untrusted/shared deployment.

### Kubernetes

Default mode mounts **no service-account token** and grants no cluster-wide RBAC:

```bash
kubectl apply -k deploy/kubernetes
kubectl -n kubeflight rollout status deployment/kubeflight
```

Helm: `helm upgrade --install kubeflight charts/kubeflight --namespace kubeflight --create-namespace`. Docker: `docker run --rm -p 8080:8080 --read-only --cap-drop ALL kubeflight:local`. Both default to the same no-token, no-cluster-wide-RBAC posture; exposure and Pod Security details are in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

### Opt-in live-cluster snapshot mode

```bash
kubectl -n kubeflight create secret generic kubeflight-api \
  --from-literal=token='replace-with-a-long-random-token'
kubectl apply -k deploy/kubernetes/live-cluster
```

Grants read-only `get/list` for Nodes, Namespaces, Pods, ServiceAccounts, StorageClasses and RuntimeClasses only — never Secrets, logs, exec, or writes. Clients authenticate to `/api/check` with `Authorization: Bearer <token>`.

### Remote deploy

Cross-ships source and installs KubeFlight as a systemd service over SSH:

```bash
./scripts/deploy-remote.sh <host> <user> --port 27754   # or KUBEFLIGHT_PORT=27754, or omit to reuse .deploy-last
./scripts/smoke-remote.sh --port 27754                  # or KUBEFLIGHT_URL=...
./scripts/deploy-remote.sh <host> <user> --uninstall     # remove
```

## What ships

- **RBAC contracts** — annotate a manifest (`kubeflight.io/requires-rbac: |` with a YAML list of `apiGroup`/`resource`/`verbs`/`resourceNames`) and KubeFlight evaluates it against submitted Roles/ClusterRoles/RoleBindings/ClusterRoleBindings.
- **GitHub Action** — `uses: zyvorai/kubeflight@v0.2.0` with `path`/`baseline`/`fail-on` inputs, a JSON/SARIF/Markdown output triple, and a step-summary write; exit codes `0` (pass), `2` (input error), `3` (threshold crossed), `4` (dry-run failed).
- **Cost model** — normalized reference rates you calibrate (`KUBEFLIGHT_COST_CPU_MONTH`, `_GIB_MONTH`, `_GIB_STORAGE_MONTH`, `_GPU_MONTH`), not a cloud bill forecast.
- **API security** — `KUBEFLIGHT_API_TOKEN`, `KUBEFLIGHT_LIVE_CLUSTER` (default `false`), body/concurrency/rate-limit guards (`KUBEFLIGHT_MAX_BODY_BYTES`, `_MAX_CONCURRENT`, `_RATE_PER_MINUTE`); live-cluster requests require both a token and the flag.
- **Offline cluster snapshot** — a JSON document of `nodes`/`pods`/`namespaces`/`serviceaccounts`/`storageclasses`/`runtimeclasses`; existing non-terminal Pods are deducted from allocatable resources before proposed replicas are placed.
- **Release checks** — `./scripts/release_check.sh` runs compile, tests, API smoke, Kubernetes self-analysis, YAML validation, and wheel build/install smoke locally; CI adds Helm, Kustomize, Docker and kind checks.

## Project layout

```text
kubeflight/
├── kubeflight/             # parser, deterministic engine, API, CLI, embedded UI
├── tests/                  # unit/API/CLI + v0.2 regression tests
├── examples/               # demo + intentionally unsafe manifests
├── deploy/kubernetes/      # restricted default install + opt-in live overlay
├── charts/kubeflight/      # Helm chart
├── scripts/                # smoke/self-analysis/release checks
├── docs/                   # architecture, rules, deployment, threat model
├── action.yml              # GitHub composite action
└── .github/workflows/      # CI, kind E2E, release/SBOM/provenance
```

**Design principles**: deterministic first · evidence and remediation with every finding · local-first, no SaaS dependency · no cluster credentials in the default deployment · unknown is not the same as safe or blocked · server dry-run/admission remains authoritative when enabled · simulation limitations are part of the output contract.

## Docs map

| Topic | Doc |
| --- | --- |
| Architecture, pipeline stages, trust boundaries | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Severities and what triggers each | [`docs/RULES.md`](docs/RULES.md) |
| Deployment modes, exposure, Pod Security | [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) |
| Assets, defaults, non-goals | [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) |
| Licensing, support, production-readiness | [`docs/FAQ.md`](docs/FAQ.md) |
| Real issues with their documented fix | [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) |
| Rendered documentation site | <https://zyvorai.github.io/kubeflight/> |

## Security

See [`SECURITY.md`](SECURITY.md) and [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) for the asset/trust model and vulnerability reporting.

## Contributing

Build/test commands and PR expectations are in [`CONTRIBUTING.md`](CONTRIBUTING.md); community conduct in [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Release history: [`CHANGELOG.md`](CHANGELOG.md).

## License

### Open source (Apache-2.0)

This repository is licensed under the [Apache License, Version 2.0](LICENSE). You may use, modify, and run it for personal, lab, and commercial production use at no charge, subject to Apache-2.0 (preserve notices / NOTICE where required).

### Enterprise

Production support, SLAs, and Zyvor Enterprise products are licensed separately. Contact [sales@zyvor.dev](mailto:sales@zyvor.dev) or see [zyvor.dev](https://zyvor.dev).
