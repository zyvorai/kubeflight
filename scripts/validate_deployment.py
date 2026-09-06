# Copyright 2026 Zyvor AI Labs · https://zyvor.dev
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
from kubeflight.engine import assess
from kubeflight.parser import parse_text
FILES=["namespace.yaml","rbac.yaml","deployment.yaml","service.yaml","pdb.yaml","networkpolicy.yaml"]
root=Path(__file__).parents[1]/"deploy/kubernetes"
resources=[]
for f in FILES: resources += parse_text((root/f).read_text(),f)
r=assess(resources).to_dict()
print(f"raw Kubernetes manifests: {r['score']}/100 {r['decision']} ({len(r['findings'])} findings)")
if r['summary']['critical'] or r['summary']['high']:
    raise SystemExit(1)
