# Troubleshooting

Real issues, with the actual fix. If your symptom isn't here,
[open an issue](https://github.com/zyvorai/kubeflight/issues).

## A manifest that "looks fine" gets flagged critical/high

Check [`docs/RULES.md`](RULES.md) for exactly what triggers each severity —
KubeFlight reports conservatively rather than guessing, so a flagged
finding usually traces to a specific, real rule (e.g. a Restricted Pod
Security violation, a missing RBAC contract, or a NetworkPolicy gap), not
a false positive. If a finding genuinely doesn't apply to your situation,
that's feedback for the rule, not a sign the tool is broken.

## Placement/scheduling simulation results don't match my real cluster

Expected if you're using an offline JSON cluster snapshot rather than a
live read-only connection — the snapshot is only as current as when it was
captured. For up-to-date placement simulation, use the opt-in live-cluster
mode ([`docs/DEPLOYMENT.md`](DEPLOYMENT.md)), which reads real node/pod
state but never requires Secret access.

## I want full certainty, not a simulation

KubeFlight says this about itself, not just as a limitation but as a
design choice: it's "a preflight simulator, not a byte-for-byte
implementation of kube-scheduler plugins, admission webhooks, CNI
dataplanes, or production traffic." For the strongest pre-apply signal
beyond simulation, use the built-in `kubectl apply --dry-run=server`
integration, which requires a real cluster and gives the API server's own
authoritative validation.

## Cost estimate doesn't match my cloud bill

The cost model is explicitly provider-neutral (see the README's "Cost
model" section) — it estimates relative change/delta, not your exact
invoice from a specific cloud provider's pricing API. Use it to catch
large, unexpected cost growth between baseline and proposed manifests, not
as a billing reconciliation tool.

## RBAC contract check fails unexpectedly

RBAC evaluation works from annotations you provide — see the README's
"RBAC contracts" section for the exact contract format. A failure usually
means the contract doesn't match what the manifest actually grants/
requires, which is the check doing its job.

## Nothing here matches

Check [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) and
[`docs/THREAT_MODEL.md`](THREAT_MODEL.md) for the full design picture,
then [open an issue](https://github.com/zyvorai/kubeflight/issues) with
your manifest (redact secrets) and the generated report.
