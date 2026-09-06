import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from kubeflight.engine import assess
from kubeflight.parser import parse_text, load_path, autodetect_path
from kubeflight.quantities import cpu_millicores, memory_bytes, QuantityError
from kubeflight.report import sarif_report, markdown_report
from kubeflight.server import app


def pod_deploy(name='app', cpu='100m', mem='64Mi', replicas=1, extra_spec=''):
    return f'''apiVersion: apps/v1
kind: Deployment
metadata: {{name: {name}}}
spec:
  replicas: {replicas}
  selector: {{matchLabels: {{app: {name}}}}}
  template:
    metadata: {{labels: {{app: {name}}}}}
    spec:
      {extra_spec}
      securityContext: {{runAsNonRoot: true, seccompProfile: {{type: RuntimeDefault}}}}
      containers:
      - name: c
        image: ghcr.io/acme/{name}:v1.2.3
        resources: {{requests: {{cpu: {cpu}, memory: {mem}}}, limits: {{memory: 128Mi}}}}
        readinessProbe: {{httpGet: {{path: /ready, port: 8080}}}}
        livenessProbe: {{httpGet: {{path: /health, port: 8080}}}}
        securityContext: {{allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {{drop: [ALL]}}}}
'''

def node(name='n1', cpu='1', mem='1Gi', labels=None):
    return {'metadata':{'name':name,'labels':labels or {'kubernetes.io/hostname':name}},'status':{'allocatable':{'cpu':cpu,'memory':mem},'conditions':[{'type':'Ready','status':'True'}]},'spec':{}}

def test_kubernetes_quantity_scientific_and_large_units():
    assert memory_bytes('129e6') == 129_000_000
    assert memory_bytes('1Pi') == 1024**5
    assert cpu_millicores('1e-3') == 1

def test_invalid_quantities_raise_instead_of_zero():
    with pytest.raises(QuantityError): memory_bytes('12Zebra')
    with pytest.raises(QuantityError): cpu_millicores('lots')

def test_invalid_quantity_becomes_critical_finding():
    r=assess(parse_text(pod_deploy(cpu='lots'))).to_dict()
    assert any(f['id']=='KF-RES-001' and f['severity']=='critical' for f in r['findings'])

def test_existing_pod_requests_are_subtracted():
    snap={'nodes':[node(cpu='1')],'pods':[{'metadata':{'name':'busy'},'spec':{'nodeName':'n1','containers':[{'name':'c','resources':{'requests':{'cpu':'600m','memory':'64Mi'}}}]},'status':{'phase':'Running'}}]}
    r=assess(parse_text(pod_deploy(cpu='500m')),snapshot=snap).to_dict()
    assert r['schedule'][0]['schedulable'] is False

def test_all_replicas_are_simulated():
    snap={'nodes':[node(cpu='1')], 'pods':[]}
    r=assess(parse_text(pod_deploy(cpu='600m',replicas=5)),snapshot=snap).to_dict()
    s=r['schedule'][0]
    assert len(s['placements'])==1 and s['unscheduled_replicas']==4 and not s['schedulable']

def test_regular_init_uses_max_not_sum():
    y=pod_deploy(cpu='900m').replace('securityContext: {runAsNonRoot: true, seccompProfile: {type: RuntimeDefault}}','''initContainers:\n      - name: init\n        image: ghcr.io/acme/init:v1\n        resources: {requests: {cpu: 900m, memory: 1Mi}}\n        securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {drop: [ALL]}}\n      securityContext: {runAsNonRoot: true, seccompProfile: {type: RuntimeDefault}}''')
    r=assess(parse_text(y),snapshot={'nodes':[node(cpu='1')],'pods':[]}).to_dict()
    assert r['schedule'][0]['schedulable'] is True

def test_native_sidecar_init_is_counted_with_app():
    y=pod_deploy(cpu='750m').replace('securityContext: {runAsNonRoot: true, seccompProfile: {type: RuntimeDefault}}','''initContainers:\n      - name: sidecar\n        image: ghcr.io/acme/side:v1\n        restartPolicy: Always\n        resources: {requests: {cpu: 300m, memory: 1Mi}}\n        securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {drop: [ALL]}}\n      securityContext: {runAsNonRoot: true, seccompProfile: {type: RuntimeDefault}}''')
    r=assess(parse_text(y),snapshot={'nodes':[node(cpu='1')],'pods':[]}).to_dict()
    assert r['schedule'][0]['schedulable'] is False

def test_runtimeclass_overhead_is_counted():
    y=pod_deploy(cpu='800m',extra_spec='runtimeClassName: kata')
    snap={'nodes':[node(cpu='1')],'pods':[],'runtimeclasses':[{'metadata':{'name':'kata'},'overhead':{'podFixed':{'cpu':'300m'}}}]}
    r=assess(parse_text(y),snapshot=snap).to_dict()
    assert r['schedule'][0]['schedulable'] is False

def test_required_node_affinity_is_enforced():
    aff='''affinity:\n        nodeAffinity:\n          requiredDuringSchedulingIgnoredDuringExecution:\n            nodeSelectorTerms:\n            - matchExpressions:\n              - {key: zone, operator: In, values: [b]}'''
    y=pod_deploy(extra_spec=aff)
    r=assess(parse_text(y),snapshot={'nodes':[node(labels={'zone':'a','kubernetes.io/hostname':'n1'})],'pods':[]}).to_dict()
    assert r['schedule'][0]['schedulable'] is False

def test_required_pod_antiaffinity_spreads_replicas():
    aff='''affinity:\n        podAntiAffinity:\n          requiredDuringSchedulingIgnoredDuringExecution:\n          - topologyKey: kubernetes.io/hostname\n            labelSelector: {matchLabels: {app: app}}'''
    y=pod_deploy(replicas=2,extra_spec=aff)
    snap={'nodes':[node('n1'),node('n2')],'pods':[]}
    r=assess(parse_text(y),snapshot=snap).to_dict()
    assert sorted(r['schedule'][0]['placements'])==['n1','n2']

def test_topology_spread_donotschedule_spreads_replicas():
    spread='''topologySpreadConstraints:\n      - maxSkew: 1\n        topologyKey: kubernetes.io/hostname\n        whenUnsatisfiable: DoNotSchedule\n        labelSelector: {matchLabels: {app: app}}'''
    y=pod_deploy(replicas=2,extra_spec=spread)
    snap={'nodes':[node('n1'),node('n2')],'pods':[]}
    r=assess(parse_text(y),snapshot=snap).to_dict()
    assert sorted(r['schedule'][0]['placements'])==['n1','n2']

def test_deletion_blast_radius_uses_baseline_graph():
    base='''apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: caller}\nspec:\n  selector: {matchLabels: {app: caller}}\n  template:\n    metadata: {labels: {app: caller}}\n    spec:\n      containers:\n      - name: c\n        image: x/c:v1\n        env: [{name: DB, value: 'db:5432'}]\n---\napiVersion: apps/v1\nkind: Deployment\nmetadata: {name: db}\nspec:\n  selector: {matchLabels: {app: db}}\n  template:\n    metadata: {labels: {app: db}}\n    spec:\n      containers: [{name: db, image: x/db:v1}]\n---\napiVersion: v1\nkind: Service\nmetadata: {name: db}\nspec: {selector: {app: db}, ports: [{port: 5432}]}\n'''
    proposed='''apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: caller}\nspec:\n  selector: {matchLabels: {app: caller}}\n  template:\n    metadata: {labels: {app: caller}}\n    spec:\n      containers:\n      - name: c\n        image: x/c:v1\n        env: [{name: DB, value: 'db:5432'}]\n'''
    r=assess(parse_text(proposed),parse_text(base)).to_dict()
    assert 'Deployment/default/caller' in r['blast_radius']

def test_image_name_does_not_create_fake_dependency():
    y='''apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: app}\nspec:\n  selector: {matchLabels: {app: app}}\n  template:\n    metadata: {labels: {app: app}}\n    spec:\n      containers: [{name: c, image: redis:7.4.0}]\n---\napiVersion: v1\nkind: Service\nmetadata: {name: redis}\nspec: {selector: {app: redis}, ports: [{port: 6379}]}\n'''
    r=assess(parse_text(y)).to_dict()
    assert 'Service/default/redis' not in r['dependencies'].get('Deployment/default/app',[])

def test_egress_networkpolicy_can_block_inferred_path():
    y='''apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: caller, namespace: app}\nspec:\n  selector: {matchLabels: {app: caller}}\n  template:\n    metadata: {labels: {app: caller}}\n    spec:\n      containers:\n      - name: c\n        image: x/c:v1\n        env: [{name: DB, value: 'db:5432'}]\n---\napiVersion: apps/v1\nkind: Deployment\nmetadata: {name: db, namespace: app}\nspec:\n  selector: {matchLabels: {app: db}}\n  template:\n    metadata: {labels: {app: db}}\n    spec: {containers: [{name: d, image: x/d:v1}]}\n---\napiVersion: v1\nkind: Service\nmetadata: {name: db, namespace: app}\nspec: {selector: {app: db}, ports: [{port: 5432}]}\n---\napiVersion: networking.k8s.io/v1\nkind: NetworkPolicy\nmetadata: {name: deny-egress, namespace: app}\nspec: {podSelector: {matchLabels: {app: caller}}, policyTypes: [Egress], egress: []}\n'''
    r=assess(parse_text(y)).to_dict()
    assert any(f['id']=='KF-NET-001' and 'egress' in f['title'] for f in r['findings'])

def test_rich_rbac_requirement_can_pass():
    y='''apiVersion: v1\nkind: ServiceAccount\nmetadata: {name: app, namespace: n}\n---\napiVersion: rbac.authorization.k8s.io/v1\nkind: Role\nmetadata: {name: reader, namespace: n}\nrules: [{apiGroups: [''], resources: [secrets], verbs: [get], resourceNames: [db]}]\n---\napiVersion: rbac.authorization.k8s.io/v1\nkind: RoleBinding\nmetadata: {name: bind, namespace: n}\nsubjects: [{kind: ServiceAccount, name: app, namespace: n}]\nroleRef: {apiGroup: rbac.authorization.k8s.io, kind: Role, name: reader}\n---\napiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: app\n  namespace: n\n  annotations:\n    kubeflight.io/requires-rbac: |\n      - apiGroup: ''\n        resource: secrets\n        verbs: [get]\n        resourceNames: [db]\nspec:\n  selector: {matchLabels: {app: app}}\n  template:\n    metadata: {labels: {app: app}}\n    spec:\n      serviceAccountName: app\n      containers: [{name: c, image: x/c:v1}]\n'''
    r=assess(parse_text(y)).to_dict()
    assert not any(f['id']=='KF-RBAC-010' for f in r['findings'])

def test_windows_hostprocess_is_blocked():
    y=pod_deploy().replace('securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {drop: [ALL]}}','securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {drop: [ALL]}, windowsOptions: {hostProcess: true}}')
    r=assess(parse_text(y)).to_dict()
    assert any(f['id']=='KF-PSS-006' and f['severity']=='critical' for f in r['findings'])

def test_explicit_uid_zero_is_rejected_even_with_run_as_non_root():
    y=pod_deploy().replace('allowPrivilegeEscalation: false','runAsUser: 0, allowPrivilegeEscalation: false')
    r=assess(parse_text(y)).to_dict()
    assert any(f['id']=='KF-PSS-009' for f in r['findings'])

def test_sarif_and_markdown_reports_are_valid():
    a=assess(parse_text('apiVersion: v1\nkind: ConfigMap\nmetadata: {name: x}\n'))
    assert json.loads(sarif_report(a))['version']=='2.1.0'
    assert 'KubeFlight' in markdown_report(a)

def test_live_cluster_api_disabled_by_default(monkeypatch):
    monkeypatch.delenv('KUBEFLIGHT_LIVE_CLUSTER',raising=False);monkeypatch.delenv('KUBEFLIGHT_API_TOKEN',raising=False)
    c=TestClient(app); y='apiVersion: v1\nkind: ConfigMap\nmetadata: {name: x}\n'
    r=c.post('/api/check',json={'manifests':y,'use_in_cluster':True})
    assert r.status_code==403

def test_api_bearer_token(monkeypatch):
    monkeypatch.setenv('KUBEFLIGHT_API_TOKEN','secret')
    c=TestClient(app); y='apiVersion: v1\nkind: ConfigMap\nmetadata: {name: x}\n'
    assert c.post('/api/check',json={'manifests':y}).status_code==401
    assert c.post('/api/check',headers={'Authorization':'Bearer secret'},json={'manifests':y}).status_code==200
