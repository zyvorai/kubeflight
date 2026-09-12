---
hero:
  eyebrow: PREFLIGHT SIMULATOR
  title: KubeFlight
  lead: "A local-first, deterministic Kubernetes preflight engine that analyzes rendered manifests, simulates scheduler placement, evaluates security, RBAC, and network policy, estimates cost, and returns an evidence-backed safety decision — without an LLM."
  swatches:
    - {label: "Apache-2.0"}
    - {label: "v0.2.0"}
    - {label: "Deterministic — no LLM"}
  highlights:
    - {value: "5", label: "severities — critical, high, medium, low, info", footnote: "1"}
    - {value: "5", label: "report formats — text, JSON, HTML, Markdown, SARIF", footnote: "2"}
    - {value: "0", label: "LLM calls used to decide whether a deployment is safe", footnote: "3"}
    - {value: "0.2.0", label: "current release version", footnote: "4"}
    - {value: "6", label: "read-only resource kinds granted in live-cluster mode", footnote: "5"}
  hub_bands:
    - {icon: "💬", title: "FAQ", description: "Licensing, support, and production-readiness questions.", href: "FAQ.md"}
    - {icon: "🛠️", title: "Troubleshooting", description: "Real operational issues with their documented fix.", href: "TROUBLESHOOTING.md"}
    - {icon: "🧭", title: "Architecture", description: "The deterministic pipeline and trust boundaries.", href: "ARCHITECTURE.md"}
    - {icon: "📋", title: "Rules", description: "The five severities and what triggers each.", href: "RULES.md"}
    - {icon: "🚀", title: "Deployment", description: "Default vs. live-cluster metadata mode.", href: "DEPLOYMENT.md"}
    - {icon: "🛡️", title: "Threat model", description: "Assets, defaults, and non-goals.", href: "THREAT_MODEL.md"}
footnotes:
  - {marker: "1", text: "The five severities and what triggers each.", href: "RULES.md", href_label: "See Rules."}
  - {marker: "2", text: "Text, JSON, HTML, Markdown/PR summary, and SARIF — from the README's v0.2.0 capabilities table.", href: "https://github.com/zyvorai/kubeflight#v020-capabilities", href_label: "See the README."}
  - {marker: "3", text: "KubeFlight is intentionally deterministic — it does not use an LLM to decide whether a deployment is safe.", href: "FAQ.md", href_label: "See FAQ."}
  - {marker: "4", text: "Current version per the project changelog.", href: "https://github.com/zyvorai/kubeflight/blob/main/CHANGELOG.md", href_label: "See CHANGELOG."}
  - {marker: "5", text: "Live-cluster mode grants read-only get/list for Nodes, Namespaces, Pods, ServiceAccounts, StorageClasses and RuntimeClasses only — never Secrets, logs, exec, or writes.", href: "https://github.com/zyvorai/kubeflight#opt-in-live-cluster-snapshot-mode", href_label: "See the README."}
---

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

## Take a closer look

=== "Scheduling"

    The simulator reads Node allocatable resources and subtracts requests
    from non-terminal Pods already assigned to each node, then greedily
    places each requested replica while applying hard placement
    predicates — accounting for application containers, init containers,
    native sidecar init containers, Pod overhead, and RuntimeClass fixed
    overhead.

=== "Network policy"

    KubeFlight constructs static dependencies from explicit
    connection-bearing fields (environment values, command/args, and
    KubeFlight dependency annotations) to submitted Services, then
    evaluates standard Kubernetes NetworkPolicy isolation in both
    directions.

=== "RBAC contracts"

    ServiceAccount presence plus explicit API group/resource/subresource/
    verb/resourceName contracts, expressed as a manifest annotation.
    KubeFlight evaluates submitted Roles, ClusterRoles, RoleBindings, and
    ClusterRoleBindings against them.

=== "Change impact"

    Baseline and proposed dependency graphs are both retained. Reverse
    traversal across their union lets deleted Services/workloads keep
    their former dependents for blast-radius analysis.

=== "Cost"

    A provider-neutral request/storage estimate and baseline delta —
    calibrated to your own CPU/GiB/GPU reference rates, not a specific
    cloud bill.

<div class="icon-badge-list" markdown="1">
- 🧩 Helm & Kustomize auto-render
- 🛡️ Restricted Pod Security checks
- 📊 Scheduler placement simulation
- 🔐 RBAC contract evaluation
- 🌐 NetworkPolicy ingress/egress
- 💰 Provider-neutral cost estimation
- 🔍 Baseline diff & blast-radius analysis
- 📄 Text/JSON/HTML/Markdown/SARIF reports
</div>
