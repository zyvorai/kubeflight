from kubeflight.engine import assess
from kubeflight.parser import parse_text

def test_network_policy_blocks_inferred_service_path():
    y='''
apiVersion: apps/v1
kind: Deployment
metadata: {name: caller, namespace: app}
spec:
  selector: {matchLabels: {app: caller}}
  template:
    metadata: {labels: {app: caller}}
    spec:
      securityContext: {runAsNonRoot: true, seccompProfile: {type: RuntimeDefault}}
      containers:
      - name: c
        image: x/c:v1
        env: [{name: DB, value: http://db:5432}]
        resources: {requests: {cpu: 1m, memory: 1Mi}, limits: {memory: 2Mi}}
        readinessProbe: {httpGet: {path: /, port: 1}}
        livenessProbe: {httpGet: {path: /, port: 1}}
        securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {drop: [ALL]}}
---
apiVersion: apps/v1
kind: Deployment
metadata: {name: db, namespace: app}
spec:
  selector: {matchLabels: {app: db}}
  template:
    metadata: {labels: {app: db}}
    spec:
      securityContext: {runAsNonRoot: true, seccompProfile: {type: RuntimeDefault}}
      containers:
      - name: db
        image: x/db:v1
        resources: {requests: {cpu: 1m, memory: 1Mi}, limits: {memory: 2Mi}}
        readinessProbe: {tcpSocket: {port: 5432}}
        livenessProbe: {tcpSocket: {port: 5432}}
        securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {drop: [ALL]}}
---
apiVersion: v1
kind: Service
metadata: {name: db, namespace: app}
spec: {selector: {app: db}, ports: [{port: 5432}]}
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: deny-db, namespace: app}
spec: {podSelector: {matchLabels: {app: db}}, policyTypes: [Ingress], ingress: []}
'''
    ids={f['id'] for f in assess(parse_text(y)).to_dict()['findings']}
    assert 'KF-NET-001' in ids

def test_required_rbac_annotation():
    y='''
apiVersion: v1
kind: ServiceAccount
metadata: {name: app, namespace: n}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata: {name: reader, namespace: n}
rules: [{apiGroups: [''], resources: [configmaps], verbs: [get]}]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: {name: bind, namespace: n}
subjects: [{kind: ServiceAccount, name: app, namespace: n}]
roleRef: {apiGroup: rbac.authorization.k8s.io, kind: Role, name: reader}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app
  namespace: n
  annotations: {kubeflight.io/requires-rbac: 'secrets:get'}
spec:
  selector: {matchLabels: {app: app}}
  template:
    metadata: {labels: {app: app}}
    spec:
      serviceAccountName: app
      securityContext: {runAsNonRoot: true, seccompProfile: {type: RuntimeDefault}}
      containers:
      - name: a
        image: x/a:v1
        resources: {requests: {cpu: 1m, memory: 1Mi}, limits: {memory: 2Mi}}
        readinessProbe: {httpGet: {path: /, port: 1}}
        livenessProbe: {httpGet: {path: /, port: 1}}
        securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {drop: [ALL]}}
'''
    ids={f['id'] for f in assess(parse_text(y)).to_dict()['findings']}
    assert 'KF-RBAC-010' in ids
