# Rules

Findings use five severities: `critical`, `high`, `medium`, `low`, `info`.

Critical findings include malformed/structurally invalid core objects, removed APIs, invalid resource quantities, privileged/HostProcess workloads, and workloads for which all replicas cannot be placed in the supplied snapshot.

High findings include Restricted Pod Security violations, blocked NetworkPolicy paths, missing required RBAC permissions, severe cost growth, and risky single-node replica concentration.

Rules are deterministic and include an evidence string plus a remediation recommendation. The engine does not silently convert unknown resource quantities to zero.
