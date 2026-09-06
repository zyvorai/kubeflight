from __future__ import annotations
import json,os,ssl,urllib.request
from pathlib import Path
from typing import Any
class ClusterError(RuntimeError):pass

def in_cluster_snapshot(timeout:float=4.0)->dict[str,Any]:
    host=os.getenv("KUBERNETES_SERVICE_HOST");port=os.getenv("KUBERNETES_SERVICE_PORT_HTTPS","443");tp=Path("/var/run/secrets/kubernetes.io/serviceaccount/token");ca=Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
    if not host or not tp.exists():raise ClusterError("Not running with an in-cluster Kubernetes service account")
    token=tp.read_text().strip();ctx=ssl.create_default_context(cafile=str(ca) if ca.exists() else None);base=f"https://{host}:{port}"
    def get(path):
        req=urllib.request.Request(base+path,headers={"Authorization":f"Bearer {token}","Accept":"application/json"})
        try:
            with urllib.request.urlopen(req,context=ctx,timeout=timeout) as r:return json.load(r)
        except Exception as exc:raise ClusterError(f"Kubernetes API request failed for {path}: {exc}") from exc
    result={}
    for key,path in (("nodes","/api/v1/nodes"),("namespaces","/api/v1/namespaces"),("pods","/api/v1/pods"),("serviceaccounts","/api/v1/serviceaccounts"),("storageclasses","/apis/storage.k8s.io/v1/storageclasses"),("runtimeclasses","/apis/node.k8s.io/v1/runtimeclasses")):
        try:result[key]=get(path).get("items",[])
        except ClusterError:
            if key in {"nodes","namespaces"}:raise
            result[key]=[]
    return result

def load_snapshot(path:str)->dict[str,Any]:return json.loads(Path(path).read_text(encoding="utf-8"))
