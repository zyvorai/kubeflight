import json
from pathlib import Path
from kubeflight.parser import load_path, parse_text
from kubeflight.engine import assess

ROOT=Path(__file__).parents[1]

def test_demo_change_cost_and_schedule():
    new=load_path(ROOT/'examples/demo/app.yaml'); old=load_path(ROOT/'examples/demo/baseline.yaml')
    snap=json.loads((ROOT/'examples/demo/cluster-snapshot.json').read_text())
    r=assess(new,old,snap).to_dict()
    assert r['resources']==4
    assert r['changed']==['Deployment/shop/payments-api']
    assert r['monthly_cost'] > r['baseline_monthly_cost']
    sr=[x for x in r['schedule'] if x['workload']=='Deployment/shop/payments-api'][0]
    assert sr['fitting_nodes']==['worker-a','worker-c']
    assert r['decision'] in {'REVIEW REQUIRED','DO NOT DEPLOY'}

def test_unsafe_is_blocked():
    r=assess(load_path(ROOT/'examples/unsafe/unsafe.yaml')).to_dict()
    assert r['decision']=='DO NOT DEPLOY'
    ids={f['id'] for f in r['findings']}
    assert 'KF-UPG-001' in ids and 'KF-SEC-020' in ids

def test_good_manifest_has_no_critical():
    y='''apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: app}\nspec:\n  replicas: 1\n  selector: {matchLabels: {app: app}}\n  template:\n    metadata: {labels: {app: app}}\n    spec:\n      securityContext: {runAsNonRoot: true, seccompProfile: {type: RuntimeDefault}}\n      containers:\n      - name: app\n        image: ghcr.io/acme/app:v1.2.3\n        resources: {requests: {cpu: 100m, memory: 64Mi}, limits: {memory: 128Mi}}\n        readinessProbe: {httpGet: {path: /ready, port: 8080}}\n        livenessProbe: {httpGet: {path: /health, port: 8080}}\n        securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {drop: [ALL]}}\n'''
    r=assess(parse_text(y)).to_dict()
    assert r['summary']['critical']==0
    assert r['summary']['high']==0

def test_scheduler_honors_basic_toleration():
    y='''apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: t}\nspec:\n  selector: {matchLabels: {app: t}}\n  template:\n    metadata: {labels: {app: t}}\n    spec:\n      tolerations: [{key: dedicated, operator: Equal, value: ai, effect: NoSchedule}]\n      securityContext: {runAsNonRoot: true, seccompProfile: {type: RuntimeDefault}}\n      containers:\n      - name: t\n        image: x/t:v1\n        resources: {requests: {cpu: 10m, memory: 1Mi}, limits: {memory: 2Mi}}\n        readinessProbe: {httpGet: {path: /, port: 1}}\n        livenessProbe: {httpGet: {path: /, port: 1}}\n        securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {drop: [ALL]}}\n'''
    snap={'nodes':[{'metadata':{'name':'n'},'spec':{'taints':[{'key':'dedicated','value':'ai','effect':'NoSchedule'}]},'status':{'allocatable':{'cpu':'1','memory':'1Gi'}}}]}
    r=assess(parse_text(y),snapshot=snap).to_dict()
    assert r['schedule'][0]['fitting_nodes']==['n']
