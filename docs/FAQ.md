# FAQ

Questions people evaluating KubeFlight actually ask, before they've
decided to adopt it.

## Licensing & cost

**Is it really free?** Yes. Apache-2.0 — use, modify, and run it for
personal, lab, and commercial production use at no charge, subject to
preserving notices. See the README's [License](https://github.com/zyvorai/kubeflight#license)
section.

**What does "Enterprise" mean here?** Production support, SLAs, and
Zyvor's other commercial products are licensed separately. Contact
sales@zyvor.dev. Nothing in this repository requires it.

## Support

**What if I find a bug?** Open a GitHub issue.

**What if I find a security vulnerability?** Do not open a public issue —
see [`SECURITY.md`](https://github.com/zyvorai/kubeflight/blob/main/SECURITY.md) for private reporting to the Zyvor
security contact, and [`docs/THREAT_MODEL.md`](THREAT_MODEL.md) for the
documented asset/trust model.

## Production readiness

**Is this production-ready?** Current version is 0.2.0. The README's own
caveat: "KubeFlight is a **preflight simulator**, not a byte-for-byte
implementation of kube-scheduler plugins, admission webhooks, CNI
dataplanes, or production traffic. Unknown facts are reported
conservatively rather than invented." Treat its verdict as one strong
signal in a review process, not a substitute for a real staging
deployment or `kubectl apply --dry-run=server` against your actual
cluster.

**Does it decide safety with AI/an LLM?** No — explicitly not: "KubeFlight
is intentionally deterministic. It does not use an LLM to decide whether a
deployment is safe." Rule IDs are stable (`KF-<AREA>-NNN`) and don't
depend on probabilistic model output (`CONTRIBUTING.md`).

## What it checks

**What does it actually evaluate?** Per the README's "v0.2.0
capabilities" table: manifest parsing/rendering (Helm/Kustomize
auto-render), schema/removed-API detection, Restricted Pod Security
checks, scheduling/placement simulation (offline snapshot or live
read-only cluster), NetworkPolicy ingress/egress, RBAC contract
evaluation, baseline/proposed diff with blast-radius analysis, cost
estimation and delta, and multi-format reports (text/JSON/HTML/Markdown/
SARIF). See [`docs/RULES.md`](RULES.md) for the five severities
(critical/high/medium/low/info) and what triggers each.

**Does it need a live cluster?** No — the default mode is fully offline
against a JSON cluster snapshot. Live, read-only cluster reads are opt-in
(see [`docs/DEPLOYMENT.md`](DEPLOYMENT.md)) and, per
[`SECURITY.md`](https://github.com/zyvorai/kubeflight/blob/main/SECURITY.md), "KubeFlight's bundled service
account never requires Secret read access."

## Integration

**Can I run it in CI?** Yes — a GitHub composite Action is documented in
the README's "GitHub Action" section, alongside a FastAPI REST API and
embedded dashboard for other integration paths.
