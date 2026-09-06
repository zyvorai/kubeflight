# Architecture

KubeFlight is a deterministic preflight pipeline:

`input -> render/parse -> structural/schema checks -> security/RBAC/network -> scheduler simulation -> change graph -> cost -> scoring -> reports`

## Trust boundaries

- **Offline CLI:** no cluster or network access is required.
- **Dashboard/API:** browser data is sent only to the KubeFlight server being used.
- **Live cluster mode:** disabled by default; requires an explicit service-account token and API bearer token.
- **Server dry-run:** optional and authoritative for API-server schema/admission behavior that static analysis cannot model.

## Scheduling model

The simulator reads Node allocatable resources and subtracts requests from non-terminal Pods already assigned to each node. It computes effective proposed Pod requests using application containers, init containers, native sidecar init containers, Pod overhead and RuntimeClass fixed overhead. It greedily places each requested replica while applying hard placement predicates.

This is intentionally not a reimplementation of every kube-scheduler framework plugin. Custom scheduler plugins, dynamic admission mutation, CSI capacity behavior and runtime-only constraints may change real placement.

## Network model

KubeFlight constructs static dependencies from explicit connection-bearing fields (environment values, command/args and KubeFlight dependency annotations) to submitted Services, then evaluates standard Kubernetes NetworkPolicy isolation in both directions. CNI-specific policy extensions are not assumed.

## Change graph

Both baseline and proposed graphs are retained. Reverse traversal across their union allows deleted Services/workloads to preserve their former dependents for blast-radius analysis.
