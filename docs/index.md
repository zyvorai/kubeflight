# KubeFlight

**Know what may break before you deploy.**

KubeFlight is an Apache-2.0, local-first Kubernetes deployment simulator
and preflight engine from Zyvor AI Labs. It analyzes rendered manifests,
optionally compares them with a baseline and a target-cluster snapshot,
simulates placement, evaluates security/RBAC/network policy, estimates
change cost, and returns an evidence-backed safety decision.

A valid manifest can still fail in production because of node capacity,
existing Pods, taints, affinity, NetworkPolicy, missing RBAC, removed
APIs, cost growth, availability constraints, or downstream dependencies.
KubeFlight puts those signals into one repeatable preflight — and it is
intentionally deterministic: it does not use an LLM to decide whether a
deployment is safe.

For the full picture — quick start, Docker/Kubernetes/Helm deployment,
GitHub Action usage, RBAC contracts, and the cost model — see the
[README on GitHub](https://github.com/zyvorai/kubeflight).

## Start here

- **[FAQ](FAQ.md)** — licensing, support, and production-readiness questions
- **[Troubleshooting](TROUBLESHOOTING.md)** — real operational issues with their documented fix
- **[Architecture](ARCHITECTURE.md)** — the deterministic pipeline and trust boundaries
- **[Rules](RULES.md)** — the five severities and what triggers each
- **[Deployment](DEPLOYMENT.md)** — default vs. live-cluster metadata mode
- **[Threat model](THREAT_MODEL.md)** — assets, defaults, and non-goals
