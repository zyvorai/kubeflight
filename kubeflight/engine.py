# Copyright 2026 Zyvor AI Labs · https://zyvor.dev
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from collections import defaultdict, deque
from copy import deepcopy
from decimal import Decimal
import hashlib, json, os, re
from typing import Any
import yaml

from .models import Assessment, Finding, ScheduleResult, SEVERITY_WEIGHT
from .parser import resource_key
from .quantities import cpu_millicores, memory_bytes, quantity, scalar_int, gib, QuantityError

TARGET_KUBERNETES = "1.37"
DEPRECATED_APIS = {
    "extensions/v1beta1": "Removed from modern Kubernetes; migrate to the stable API for this kind.",
    "apps/v1beta1": "Removed; use apps/v1.", "apps/v1beta2": "Removed; use apps/v1.",
    "networking.k8s.io/v1beta1": "Removed; use networking.k8s.io/v1.",
    "policy/v1beta1": "Removed; use policy/v1.", "batch/v1beta1": "Removed for CronJob; use batch/v1.",
    "admissionregistration.k8s.io/v1beta1": "Removed; use admissionregistration.k8s.io/v1.",
}
WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Pod"}
SAFE_SYSCTLS_137 = {
    "kernel.shm_rmid_forced", "net.ipv4.ip_local_port_range", "net.ipv4.ip_unprivileged_port_start",
    "net.ipv4.ip_local_reserved_ports", "net.ipv4.tcp_syncookies", "net.ipv4.ping_group_range",
    "net.ipv4.ip_unprivileged_port_start", "net.ipv4.tcp_keepalive_time", "net.ipv4.tcp_fin_timeout",
    "net.ipv4.tcp_keepalive_intvl", "net.ipv4.tcp_keepalive_probes",
}
ALLOWED_SELINUX_TYPES = {"container_t", "container_init_t", "container_kvm_t", "container_engine_t"}
ALLOWED_CAP_ADD = {"NET_BIND_SERVICE"}


def _finding(fid, severity, category, title, res, evidence, recommendation):
    return Finding(fid, severity, category, title, res, evidence, recommendation)

def _hash(obj: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def _pod_spec(obj: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    kind = obj.get("kind"); spec = obj.get("spec") or {}
    if kind == "Pod": return spec, obj.get("metadata") or {}
    if kind == "CronJob":
        tpl = (((spec.get("jobTemplate") or {}).get("spec") or {}).get("template") or {})
        return tpl.get("spec") or {}, tpl.get("metadata") or {}
    if kind in {"Deployment", "StatefulSet", "DaemonSet", "Job"}:
        tpl = spec.get("template") or {}
        return tpl.get("spec") or {}, tpl.get("metadata") or {}
    return None, {}

def _replicas(obj: dict[str, Any]) -> int:
    kind=obj.get("kind")
    if kind in {"Pod","Job","CronJob","DaemonSet"}: return 1
    try: return max(0, int((obj.get("spec") or {}).get("replicas", 1) or 1))
    except Exception: return 1

def _selector_labels(obj: dict[str, Any]) -> dict[str, str]:
    if obj.get("kind") == "Pod": return (obj.get("metadata") or {}).get("labels") or {}
    return (((obj.get("spec") or {}).get("template") or {}).get("metadata") or {}).get("labels") or {}

def _selector_matches(selector: dict[str, Any] | None, labels: dict[str, str]) -> bool:
    if selector is None: return False
    ml = selector.get("matchLabels") or {}
    if any(labels.get(k) != str(v) for k, v in ml.items()): return False
    for exp in selector.get("matchExpressions") or []:
        key=exp.get("key"); op=exp.get("operator"); vals=[str(v) for v in exp.get("values") or []]; actual=labels.get(key)
        if op == "In" and actual not in vals: return False
        if op == "NotIn" and actual in vals: return False
        if op == "Exists" and key not in labels: return False
        if op == "DoesNotExist" and key in labels: return False
    return True

def _plain_selector_matches(selector: dict[str, str], labels: dict[str, str]) -> bool:
    return bool(selector) and all(labels.get(k) == str(v) for k,v in selector.items())

# ---------- resource accounting ----------

def _container_requests(c: dict[str, Any]) -> dict[str, int]:
    req=((c.get("resources") or {}).get("requests") or {})
    out: dict[str,int]={}
    for k,v in req.items():
        if k == "cpu": out[k]=cpu_millicores(v)
        elif k in {"memory","ephemeral-storage"}: out[k]=memory_bytes(v)
        else: out[k]=scalar_int(v)
    return out

def _add(a: dict[str,int], b: dict[str,int]) -> dict[str,int]:
    out=dict(a)
    for k,v in b.items(): out[k]=out.get(k,0)+v
    return out

def _max_resources(a: dict[str,int], b: dict[str,int]) -> dict[str,int]:
    keys=set(a)|set(b); return {k:max(a.get(k,0), b.get(k,0)) for k in keys}

def _pod_requests(pod: dict[str,Any]) -> dict[str,int]:
    # Kubernetes effective request: steady-state application + native sidecars,
    # compared against every init stage. Native sidecar init containers
    # (restartPolicy: Always) keep running and accumulate for later init stages.
    app: dict[str,int]={}
    for c in pod.get("containers") or []: app=_add(app,_container_requests(c))
    sidecars: dict[str,int]={}; peak: dict[str,int]={}
    for c in pod.get("initContainers") or []:
        req=_container_requests(c)
        if c.get("restartPolicy") == "Always":
            sidecars=_add(sidecars,req)
            peak=_max_resources(peak, sidecars)
        else:
            peak=_max_resources(peak, _add(sidecars, req))
    effective=_max_resources(_add(app,sidecars),peak)
    overhead=pod.get("overhead") or {}
    for k,v in overhead.items():
        if k=="cpu": effective[k]=effective.get(k,0)+cpu_millicores(v)
        elif k in {"memory","ephemeral-storage"}: effective[k]=effective.get(k,0)+memory_bytes(v)
        else: effective[k]=effective.get(k,0)+scalar_int(v)
    return effective

def _resource_label(k:str, v:int)->str:
    if k=="cpu": return f"{v}m"
    if k in {"memory","ephemeral-storage"}: return f"{v} bytes"
    return str(v)

# ---------- schema / manifest checks ----------

def _schema_findings(o:dict[str,Any], rk:str)->list[Finding]:
    out=[]
    if not o.get("apiVersion") or not o.get("kind") or not (o.get("metadata") or {}).get("name"):
        return [_finding("KF-MAN-001","critical","manifest","Malformed Kubernetes object",rk,"apiVersion/kind/metadata.name are required","Fix the manifest structure.")]
    kind=o.get("kind"); spec=o.get("spec") or {}
    if kind in {"Deployment","StatefulSet","DaemonSet"}:
        selector=spec.get("selector")
        tpl=(spec.get("template") or {})
        if not isinstance(selector,dict) or not isinstance(tpl,dict):
            out.append(_finding("KF-MAN-010","critical","schema",f"{kind} requires spec.selector and spec.template",rk,"Required workload fields are missing","Add a selector and Pod template that satisfy the Kubernetes API schema."))
        else:
            labels=(tpl.get("metadata") or {}).get("labels") or {}
            if selector.get("matchLabels") and not _plain_selector_matches(selector.get("matchLabels") or {}, labels):
                out.append(_finding("KF-MAN-011","critical","schema","Workload selector does not match Pod template labels",rk,"spec.selector.matchLabels is not a subset of spec.template.metadata.labels","Align the selector and Pod template labels."))
    if kind=="Service" and not isinstance(spec.get("ports",[]),list):
        out.append(_finding("KF-MAN-012","critical","schema","Service ports must be a list",rk,"spec.ports is not a list","Use Kubernetes Service v1 schema."))
    if kind=="NetworkPolicy" and o.get("apiVersion")!="networking.k8s.io/v1":
        out.append(_finding("KF-MAN-013","high","schema","NetworkPolicy should use networking.k8s.io/v1",rk,f"apiVersion={o.get('apiVersion')}","Use networking.k8s.io/v1."))
    return out

# ---------- Restricted PSS checks ----------

def _security_findings(obj:dict[str,Any], pod:dict[str,Any], rk:str)->list[Finding]:
    out=[]; psc=pod.get("securityContext") or {}
    if pod.get("hostNetwork") or pod.get("hostPID") or pod.get("hostIPC"):
        out.append(_finding("KF-PSS-001","critical","security","Host namespace sharing violates Restricted Pod Security",rk,"hostNetwork/hostPID/hostIPC must be false","Disable host namespace sharing."))
    if any("hostPath" in v for v in pod.get("volumes") or []):
        out.append(_finding("KF-PSS-002","high","security","hostPath volume violates Restricted Pod Security",rk,"Pod mounts a hostPath volume","Use PVC, projected, configMap, secret, emptyDir or another allowed volume source."))
    for s in (psc.get("sysctls") or []):
        if s.get("name") not in SAFE_SYSCTLS_137:
            out.append(_finding("KF-PSS-003","high","security",f"Unsafe sysctl: {s.get('name')}",rk,"Sysctl is outside the Restricted safe set","Remove the sysctl or enforce it through a dedicated privileged workload boundary."))
    seccomp=(psc.get("seccompProfile") or {}).get("type")
    selinux=(psc.get("seLinuxOptions") or {})
    if selinux.get("user") or selinux.get("role") or (selinux.get("type") and selinux.get("type") not in ALLOWED_SELINUX_TYPES):
        out.append(_finding("KF-PSS-004","high","security","SELinux options violate Restricted policy",rk,f"seLinuxOptions={selinux}","Use an allowed SELinux type and do not set user/role."))
    apparmor=((obj.get("metadata") or {}).get("annotations") or {})
    for k,v in apparmor.items():
        if k.startswith("container.apparmor.security.beta.kubernetes.io/") and not (str(v)=="runtime/default" or str(v).startswith("localhost/")):
            out.append(_finding("KF-PSS-005","high","security","AppArmor profile violates Restricted policy",rk,f"{k}={v}","Use runtime/default or a localhost profile."))
    all_containers=list(pod.get("initContainers") or [])+list(pod.get("containers") or [])+list(pod.get("ephemeralContainers") or [])
    for c in all_containers:
        name=c.get("name","container"); sc=c.get("securityContext") or {}
        if sc.get("windowsOptions",{}).get("hostProcess") is True:
            out.append(_finding("KF-PSS-006","critical","security",f"Windows HostProcess enabled: {name}",rk,"windowsOptions.hostProcess=true","Disable HostProcess for Restricted workloads."))
        if sc.get("privileged") is True:
            out.append(_finding("KF-SEC-020","critical","security",f"Privileged container: {name}",rk,"securityContext.privileged=true","Remove privileged mode."))
        if sc.get("allowPrivilegeEscalation") is not False:
            out.append(_finding("KF-SEC-021","high","security",f"Privilege escalation not disabled: {name}",rk,"allowPrivilegeEscalation is not false","Set allowPrivilegeEscalation: false."))
        caps=sc.get("capabilities") or {}; drops=caps.get("drop") or []; adds=set(caps.get("add") or [])
        if "ALL" not in drops or not adds.issubset(ALLOWED_CAP_ADD):
            out.append(_finding("KF-SEC-022","high","security",f"Capabilities violate Restricted policy: {name}",rk,f"drop={drops}, add={sorted(adds)}","Drop ALL capabilities and add back only NET_BIND_SERVICE when required."))
        csec=(sc.get("seccompProfile") or {}).get("type") or seccomp
        if csec not in {"RuntimeDefault","Localhost"}:
            out.append(_finding("KF-SEC-011","high","security",f"Seccomp profile missing/invalid: {name}",rk,"Restricted policy requires RuntimeDefault or Localhost","Set seccompProfile.type: RuntimeDefault."))
        run_non_root=sc.get("runAsNonRoot",psc.get("runAsNonRoot")); uid=sc.get("runAsUser",psc.get("runAsUser"))
        if uid is not None and int(uid)==0:
            out.append(_finding("KF-PSS-009","high","security",f"Container explicitly runs as UID 0: {name}",rk,"runAsUser=0 violates Restricted policy","Use a non-zero UID."))
        elif run_non_root is not True and uid is None:
            out.append(_finding("KF-SEC-010","high","security",f"Non-root execution not proven: {name}",rk,"runAsNonRoot is not true and runAsUser is not a known non-zero UID","Set runAsNonRoot: true or a non-zero runAsUser."))
        capparmor=(sc.get("appArmorProfile") or {}).get("type")
        if capparmor and capparmor not in {"RuntimeDefault","Localhost"}:
            out.append(_finding("KF-PSS-010","high","security",f"AppArmor profile violates Restricted policy: {name}",rk,f"appArmorProfile.type={capparmor}","Use RuntimeDefault or Localhost."))
        cselinux=sc.get("seLinuxOptions") or {}
        if cselinux.get("user") or cselinux.get("role") or (cselinux.get("type") and cselinux.get("type") not in ALLOWED_SELINUX_TYPES):
            out.append(_finding("KF-PSS-011","high","security",f"SELinux options violate Restricted policy: {name}",rk,f"seLinuxOptions={cselinux}","Use an allowed SELinux type and do not set user/role."))
        if sc.get("readOnlyRootFilesystem") is not True:
            out.append(_finding("KF-SEC-023","low","security",f"Writable root filesystem: {name}",rk,"readOnlyRootFilesystem is not true","Set readOnlyRootFilesystem: true where compatible."))
        for probe_name in ("livenessProbe","readinessProbe","startupProbe"):
            h=((c.get(probe_name) or {}).get("httpGet") or {}).get("host")
            if h: out.append(_finding("KF-PSS-007","high","security",f"Probe host field set: {name}",rk,f"{probe_name}.httpGet.host={h}","Remove the explicit host field."))
        for hook in ("postStart","preStop"):
            h=((((c.get("lifecycle") or {}).get(hook) or {}).get("httpGet") or {}).get("host"))
            if h: out.append(_finding("KF-PSS-008","high","security",f"Lifecycle host field set: {name}",rk,f"lifecycle.{hook}.httpGet.host={h}","Remove the explicit host field."))
    return out

def _reliability_findings(obj,pod,rk):
    out=[]
    for c in pod.get("containers") or []:
        name=c.get("name","container"); res=c.get("resources") or {}; req=res.get("requests") or {}; lim=res.get("limits") or {}
        if "cpu" not in req or "memory" not in req: out.append(_finding("KF-REL-001","medium","reliability",f"Resource requests incomplete: {name}",rk,"CPU and/or memory request missing","Set realistic CPU and memory requests."))
        if "memory" not in lim: out.append(_finding("KF-REL-002","low","reliability",f"Memory limit missing: {name}",rk,"resources.limits.memory missing","Set a memory limit after validating workload behavior."))
        img=str(c.get("image", "")); last=img.rsplit("/",1)[-1]
        if not img or img.endswith(":latest") or (":" not in last and "@sha256:" not in img): out.append(_finding("KF-SUP-001","medium","supply-chain",f"Unpinned image: {name}",rk,f"image={img or '<missing>'}","Pin an immutable digest or explicit version tag."))
        if not c.get("readinessProbe"): out.append(_finding("KF-REL-003","medium","reliability",f"Readiness probe missing: {name}",rk,"No readinessProbe configured","Add a readiness probe before production rollout."))
        if not c.get("livenessProbe"): out.append(_finding("KF-REL-004","low","reliability",f"Liveness probe missing: {name}",rk,"No livenessProbe configured","Add a liveness/startup strategy appropriate to the application."))
    return out

# ---------- dependency graph ----------

def _connection_text(pod:dict[str,Any], meta:dict[str,Any])->str:
    parts=[]
    anns=meta.get("annotations") or {}
    for k,v in anns.items():
        if k.startswith("kubeflight.io/depend") or k.startswith("kubeflight.io/connect"): parts.append(str(v))
    for c in list(pod.get("containers") or [])+list(pod.get("initContainers") or []):
        parts.extend(str(x) for x in c.get("command") or [])
        parts.extend(str(x) for x in c.get("args") or [])
        for e in c.get("env") or []:
            if "value" in e: parts.append(str(e.get("value")))
    return "\n".join(parts)

def _dependencies(resources:list[dict[str,Any]])->dict[str,list[str]]:
    services=[]; workloads=[]
    for o in resources:
        if o.get("kind")=="Service": services.append(o)
        if o.get("kind") in WORKLOAD_KINDS: workloads.append(o)
    svc_to_workload={}
    for s in services:
        sel=(s.get("spec") or {}).get("selector") or {}; sk=resource_key(s)
        svc_to_workload[sk]=[resource_key(w) for w in workloads if _plain_selector_matches(sel,_selector_labels(w))]
    names={((s.get("metadata") or {}).get("namespace","default"),(s.get("metadata") or {}).get("name")):resource_key(s) for s in services}
    graph=defaultdict(set)
    for w in workloads:
        wk=resource_key(w); meta=w.get("metadata") or {}; ns=meta.get("namespace","default"); pod,tmeta=_pod_spec(w); text=_connection_text(pod or {}, {**meta,"annotations":{**(meta.get("annotations") or {}),**(tmeta.get("annotations") or {})}})
        for (sns,sname),sk in names.items():
            # Allow service, service.ns and service.ns.svc references. Do not scan image fields.
            pat=rf"(?<![A-Za-z0-9-]){re.escape(sname)}(?:\.{re.escape(sns)}(?:\.svc(?:\.cluster\.local)?)?)?(?=[:/\s'\"\)]|$)"
            if re.search(pat,text) and (sns==ns or f".{sns}" in text): graph[wk].add(sk)
    for sk,targets in svc_to_workload.items():
        for t in targets: graph[sk].add(t)
    return {k:sorted(v) for k,v in sorted(graph.items())}

def _blast(changed:list[str], *graphs:dict[str,list[str]])->list[str]:
    reverse=defaultdict(set)
    for deps in graphs:
        for a,bs in deps.items():
            for b in bs: reverse[b].add(a)
    seen=set(changed); q=deque(changed)
    while q:
        cur=q.popleft()
        for dep in reverse.get(cur,()):
            if dep not in seen: seen.add(dep); q.append(dep)
    return sorted(seen-set(changed))

# ---------- NetworkPolicy ----------

def _namespace_labels(resources, snapshot)->dict[str,dict[str,str]]:
    out={"default":{"kubernetes.io/metadata.name":"default"}}
    for o in resources:
        if o.get("kind")=="Namespace":
            m=o.get("metadata") or {}; n=m.get("name"); out[n]={**(m.get("labels") or {}),"kubernetes.io/metadata.name":n}
    for o in (snapshot or {}).get("namespaces") or []:
        m=o.get("metadata") or {}; n=m.get("name"); out[n]={**(m.get("labels") or {}),"kubernetes.io/metadata.name":n}
    return out

def _ports_for_service(svc:dict[str,Any])->set[int|str]:
    out=set()
    for p in (svc.get("spec") or {}).get("ports") or []:
        port=p.get("targetPort",p.get("port")); out.add(port)
    return out

def _rule_ports_allow(rule:dict[str,Any], svc_ports:set[int|str])->bool:
    ports=rule.get("ports")
    if ports is None: return True
    for p in ports:
        rp=p.get("port")
        if rp is None: return True
        if isinstance(rp,int) and p.get("endPort"):
            if any(isinstance(x,int) and rp<=x<=int(p["endPort"]) for x in svc_ports): return True
        elif rp in svc_ports: return True
    return False

def _peer_allows(peer:dict[str,Any], src_ns:str, src_labels:dict[str,str], ns_labels:dict[str,dict[str,str]])->bool|None:
    if peer.get("ipBlock") is not None: return None
    ns_sel=peer.get("namespaceSelector"); pod_sel=peer.get("podSelector")
    ns_ok=True if ns_sel is None else _selector_matches(ns_sel,ns_labels.get(src_ns,{"kubernetes.io/metadata.name":src_ns}))
    pod_ok=True if pod_sel is None else _selector_matches(pod_sel,src_labels)
    return ns_ok and pod_ok

def _network_policy_findings(resources:list[dict[str,Any]], deps:dict[str,list[str]], snapshot=None)->list[Finding]:
    objs={resource_key(o):o for o in resources}; nps=[o for o in resources if o.get("kind")=="NetworkPolicy"]; nsl=_namespace_labels(resources,snapshot); out=[]
    for source,targets in deps.items():
        so=objs.get(source)
        if not so or so.get("kind") not in WORKLOAD_KINDS: continue
        sm=so.get("metadata") or {}; sns=sm.get("namespace","default"); slabels=_selector_labels(so)
        for svc_key in targets:
            svc=objs.get(svc_key)
            if not svc or svc.get("kind")!="Service": continue
            ports=_ports_for_service(svc)
            for dest in deps.get(svc_key,[]):
                dobj=objs.get(dest)
                if not dobj: continue
                dm=dobj.get("metadata") or {}; dns=dm.get("namespace","default"); dlabels=_selector_labels(dobj)
                ingress=[]; egress=[]
                for np in nps:
                    nm=np.get("metadata") or {}; spec=np.get("spec") or {}; nns=nm.get("namespace","default")
                    if nns==dns and _selector_matches(spec.get("podSelector") or {},dlabels):
                        types=spec.get("policyTypes") or (["Ingress"] if "ingress" in spec else [])
                        if "Ingress" in types: ingress.append(np)
                    if nns==sns and _selector_matches(spec.get("podSelector") or {},slabels):
                        types=spec.get("policyTypes") or (["Ingress"] if "ingress" in spec else []) + (["Egress"] if "egress" in spec else [])
                        if "Egress" in types: egress.append(np)
                ingress_allowed=not ingress
                unknown=False
                if ingress:
                    for np in ingress:
                        for rule in (np.get("spec") or {}).get("ingress") or []:
                            if not _rule_ports_allow(rule,ports): continue
                            peers=rule.get("from")
                            if peers is None: ingress_allowed=True; break
                            for peer in peers:
                                r=_peer_allows(peer,sns,slabels,nsl)
                                if r is True: ingress_allowed=True; break
                                if r is None: unknown=True
                            if ingress_allowed: break
                        if ingress_allowed: break
                egress_allowed=not egress
                if egress:
                    for np in egress:
                        for rule in (np.get("spec") or {}).get("egress") or []:
                            if not _rule_ports_allow(rule,ports): continue
                            peers=rule.get("to")
                            if peers is None: egress_allowed=True; break
                            for peer in peers:
                                r=_peer_allows(peer,dns,dlabels,nsl)
                                if r is True: egress_allowed=True; break
                                if r is None: unknown=True
                            if egress_allowed: break
                        if egress_allowed: break
                if (not ingress_allowed or not egress_allowed) and not unknown:
                    side="ingress" if not ingress_allowed else "egress"
                    out.append(_finding("KF-NET-001","high","network",f"NetworkPolicy blocks inferred {side} path to {svc_key.split('/')[-1]}",source,f"{source} -> {svc_key} -> {dest} is statically denied on {side}","Add a narrowly scoped policy rule for the source/destination and required port."))
    seen=set(); ded=[]
    for f in out:
        k=(f.id,f.resource,f.title,f.evidence)
        if k not in seen: seen.add(k); ded.append(f)
    return ded

# ---------- RBAC ----------

def _parse_rbac_requirements(raw:Any, default_ns:str)->list[dict[str,Any]]:
    if not raw: return []
    s=str(raw).strip()
    try:
        obj=yaml.safe_load(s)
    except Exception: obj=None
    if isinstance(obj,list):
        out=[]
        for x in obj:
            if not isinstance(x,dict): continue
            out.append({"apiGroup":str(x.get("apiGroup","")),"resource":str(x.get("resource","")),"verbs":list(x.get("verbs") or []),"namespace":x.get("namespace",default_ns),"resourceNames":list(x.get("resourceNames") or [])})
        return out
    out=[]
    for tok in s.split(','):
        tok=tok.strip()
        if ':' in tok:
            r,v=tok.rsplit(':',1); out.append({"apiGroup":"","resource":r.strip(),"verbs":[v.strip()],"namespace":default_ns,"resourceNames":[]})
    return out

def _rbac_requirement_findings(resources:list[dict[str,Any]])->list[Finding]:
    roles={}; crs={}; binds=[]
    for o in resources:
        kind=o.get("kind"); m=o.get("metadata") or {}; n=m.get("name"); ns=m.get("namespace","default")
        if kind=="Role": roles[(ns,n)]=o.get("rules") or []
        elif kind=="ClusterRole": crs[n]=o.get("rules") or []
        elif kind in {"RoleBinding","ClusterRoleBinding"}: binds.append(o)
    def rules_for(sa_ns,sa_name):
        rr=[]
        for b in binds:
            bm=b.get("metadata") or {}; bns=bm.get("namespace","default")
            if not any(s.get("kind")=="ServiceAccount" and s.get("name")==sa_name and s.get("namespace",bns)==sa_ns for s in b.get("subjects") or []): continue
            ref=b.get("roleRef") or {}
            if ref.get("kind")=="ClusterRole": rr.extend(crs.get(ref.get("name"),[]))
            elif ref.get("kind")=="Role" and b.get("kind")=="RoleBinding" and bns==sa_ns: rr.extend(roles.get((bns,ref.get("name")),[]))
        return rr
    out=[]
    for o in resources:
        pod,tmeta=_pod_spec(o)
        if pod is None: continue
        m=o.get("metadata") or {}; anns={**(m.get("annotations") or {}),**(tmeta.get("annotations") or {})}; raw=anns.get("kubeflight.io/requires-rbac")
        if not raw: continue
        ns=m.get("namespace","default"); sa=pod.get("serviceAccountName","default"); rules=rules_for(ns,sa)
        for req in _parse_rbac_requirements(raw,ns):
            resource=req["resource"]; verbs=req["verbs"]; api=req["apiGroup"]; rns=req["resourceNames"]
            for verb in verbs:
                ok=False
                for r in rules:
                    if verb not in (r.get("verbs") or []) and "*" not in (r.get("verbs") or []): continue
                    if api not in (r.get("apiGroups") or []) and "*" not in (r.get("apiGroups") or []): continue
                    if resource not in (r.get("resources") or []) and "*" not in (r.get("resources") or []): continue
                    allowed_names=r.get("resourceNames") or []
                    if rns and allowed_names and not set(rns).issubset(set(allowed_names)): continue
                    ok=True; break
                if not ok:
                    out.append(_finding("KF-RBAC-010","high","rbac",f"Required permission not proven: {api or 'core'}/{resource}:{verb}",resource_key(o),f"ServiceAccount {ns}/{sa} lacks the required permission in submitted RBAC","Grant the minimum permission or correct kubeflight.io/requires-rbac."))
    return out

# ---------- scheduler ----------

def _tolerates(taint:dict[str,Any], tolerations:list[dict[str,Any]])->bool:
    tkey=taint.get("key",""); tval=str(taint.get("value","")); teffect=taint.get("effect","")
    for tol in tolerations:
        if tol.get("effect") and tol.get("effect")!=teffect: continue
        op=tol.get("operator","Equal"); key=tol.get("key","")
        if op=="Exists" and (not key or key==tkey): return True
        if op=="Equal" and key==tkey and str(tol.get("value",""))==tval: return True
    return False

def _node_affinity_ok(pod:dict[str,Any], labels:dict[str,str])->bool:
    req=((((pod.get("affinity") or {}).get("nodeAffinity") or {}).get("requiredDuringSchedulingIgnoredDuringExecution") or {}))
    terms=req.get("nodeSelectorTerms") or []
    if not terms: return True
    def expr_ok(e):
        k=e.get("key"); op=e.get("operator"); vals=[str(x) for x in e.get("values") or []]; actual=labels.get(k)
        if op=="In": return actual in vals
        if op=="NotIn": return actual is not None and actual not in vals
        if op=="Exists": return k in labels
        if op=="DoesNotExist": return k not in labels
        if op in {"Gt","Lt"}:
            try: return int(actual) > int(vals[0]) if op=="Gt" else int(actual) < int(vals[0])
            except Exception: return False
        return False
    return any(all(expr_ok(e) for e in t.get("matchExpressions") or []) for t in terms)

def _node_capacity(n:dict[str,Any])->dict[str,int]:
    alloc=((n.get("status") or {}).get("allocatable") or (n.get("status") or {}).get("capacity") or {})
    out={}
    for k,v in alloc.items():
        try:
            if k=="cpu": out[k]=cpu_millicores(v)
            elif k in {"memory","ephemeral-storage"}: out[k]=memory_bytes(v)
            else: out[k]=scalar_int(v)
        except QuantityError: out[k]=0
    return out

def _fits(req:dict[str,int], avail:dict[str,int])->list[str]:
    errs=[]
    for k,v in req.items():
        if v>avail.get(k,0): errs.append(f"insufficient {k} ({_resource_label(k,v)} requested, {_resource_label(k,avail.get(k,0))} available)")
    return errs

def _existing_reservations(snapshot)->dict[str,dict[str,int]]:
    res=defaultdict(dict)
    for p in (snapshot or {}).get("pods") or []:
        if (p.get("status") or {}).get("phase") in {"Succeeded","Failed"}: continue
        node=(p.get("spec") or {}).get("nodeName")
        if not node: continue
        try: req=_pod_requests(p.get("spec") or {})
        except QuantityError: continue
        res[node]=_add(res[node],req)
    return res


def _pod_labels(p:dict[str,Any])->dict[str,str]:
    return (p.get("metadata") or {}).get("labels") or {}

def _pods_on_node(snapshot,node_name:str)->list[dict[str,Any]]:
    return [p for p in (snapshot or {}).get("pods") or [] if (p.get("spec") or {}).get("nodeName")==node_name and (p.get("status") or {}).get("phase") not in {"Succeeded","Failed"}]

def _term_namespace_ok(term:dict[str,Any], pod_obj:dict[str,Any], workload_ns:str, ns_labels:dict[str,dict[str,str]])->bool:
    pm=pod_obj.get("metadata") or {}; pns=pm.get("namespace","default")
    if term.get("namespaces") is not None and pns not in term.get("namespaces",[]): return False
    if term.get("namespaceSelector") is not None and not _selector_matches(term.get("namespaceSelector") or {}, ns_labels.get(pns,{"kubernetes.io/metadata.name":pns})): return False
    if term.get("namespaces") is None and term.get("namespaceSelector") is None and pns!=workload_ns: return False
    return True

def _pod_affinity_ok(pod:dict[str,Any], node:dict[str,Any], nodes:list[dict[str,Any]], snapshot, workload_ns:str, ns_labels:dict[str,dict[str,str]], synthetic:list[dict[str,Any]])->tuple[bool,list[str]]:
    errs=[]; affinity=pod.get("affinity") or {}; node_labels=(node.get("metadata") or {}).get("labels") or {}; all_pods=list((snapshot or {}).get("pods") or [])+synthetic
    for mode,key in (("affinity","podAffinity"),("anti-affinity","podAntiAffinity")):
        terms=(((affinity.get(key) or {}).get("requiredDuringSchedulingIgnoredDuringExecution") or []))
        for term in terms:
            topo=term.get("topologyKey")
            if not topo: continue
            domain=node_labels.get(topo)
            if domain is None:
                errs.append(f"required pod {mode} topologyKey {topo} missing"); continue
            found=False
            for ep in all_pods:
                if not _term_namespace_ok(term,ep,workload_ns,ns_labels): continue
                if not _selector_matches(term.get("labelSelector") or {},_pod_labels(ep)): continue
                enode=(ep.get("spec") or {}).get("nodeName")
                en=next((x for x in nodes if (x.get("metadata") or {}).get("name")==enode),None)
                if en and ((en.get("metadata") or {}).get("labels") or {}).get(topo)==domain: found=True; break
            if mode=="affinity" and not found: errs.append(f"required podAffinity not satisfied on {topo}")
            if mode=="anti-affinity" and found: errs.append(f"required podAntiAffinity violated on {topo}")
    return not errs,errs

def _topology_spread_ok(pod:dict[str,Any], node:dict[str,Any], eligible_nodes:list[dict[str,Any]], snapshot, synthetic:list[dict[str,Any]])->tuple[bool,list[str]]:
    errs=[]; labels=(pod.get("_kubeflight_labels") or {})
    all_pods=list((snapshot or {}).get("pods") or [])+synthetic
    for c in pod.get("topologySpreadConstraints") or []:
        if c.get("whenUnsatisfiable")!="DoNotSchedule": continue
        key=c.get("topologyKey"); max_skew=int(c.get("maxSkew",1)); selector=c.get("labelSelector") or {}
        domain=((node.get("metadata") or {}).get("labels") or {}).get(key)
        if domain is None: errs.append(f"topologySpread topologyKey {key} missing"); continue
        domains={((n.get("metadata") or {}).get("labels") or {}).get(key) for n in eligible_nodes}; domains.discard(None)
        counts={d:0 for d in domains}
        for ep in all_pods:
            if not _selector_matches(selector,_pod_labels(ep)): continue
            ename=(ep.get("spec") or {}).get("nodeName")
            en=next((n for n in eligible_nodes if (n.get("metadata") or {}).get("name")==ename),None)
            if en:
                d=((en.get("metadata") or {}).get("labels") or {}).get(key)
                if d in counts: counts[d]+=1
        if domain in counts: counts[domain]+=1
        if counts and max(counts.values())-min(counts.values())>max_skew: errs.append(f"topology spread maxSkew {max_skew} would be exceeded on {key}")
    return not errs,errs

def _schedule(resources, snapshot)->list[ScheduleResult]:
    if not snapshot: return []
    nodes=snapshot.get("nodes") or []; existing=_existing_reservations(snapshot); out=[]; nsl=_namespace_labels([],snapshot)
    runtime_overhead={}
    for rc in snapshot.get("runtimeclasses") or []:
        m=rc.get("metadata") or {}; fixed=((rc.get("overhead") or {}).get("podFixed") or {}); runtime_overhead[m.get("name")]=fixed
    base_avail={}
    for n in nodes:
        name=(n.get("metadata") or {}).get("name","node"); cap=_node_capacity(n); used=existing.get(name,{})
        base_avail[name]={k:max(0,cap.get(k,0)-used.get(k,0)) for k in set(cap)|set(used)}
    for o in resources:
        if o.get("kind") not in WORKLOAD_KINDS: continue
        pod,tmeta=_pod_spec(o); pod=deepcopy(pod or {}); rk=resource_key(o); reps=_replicas(o); wm=o.get("metadata") or {}; wns=wm.get("namespace","default"); labels=_selector_labels(o); pod["_kubeflight_labels"]=labels
        try:
            req=_pod_requests(pod)
            rcname=pod.get("runtimeClassName")
            if rcname and rcname in runtime_overhead:
                for k,v in runtime_overhead[rcname].items():
                    if k=="cpu": req[k]=req.get(k,0)+cpu_millicores(v)
                    elif k in {"memory","ephemeral-storage"}: req[k]=req.get(k,0)+memory_bytes(v)
                    else:req[k]=req.get(k,0)+scalar_int(v)
        except QuantityError as e:
            out.append(ScheduleResult(rk,reps,[],[],reps,{"quantity":[str(e)]})); continue
        avail=deepcopy(base_avail); placements=[]; reasons_all={}; eligible=[]; node_by_name={(n.get("metadata") or {}).get("name","node"):n for n in nodes}
        # Static hard predicates first.
        for n in nodes:
            meta=n.get("metadata") or {}; status=n.get("status") or {}; spec=n.get("spec") or {}; name=meta.get("name","node"); nl=meta.get("labels") or {}; errs=[]
            if spec.get("unschedulable"): errs.append("node is unschedulable")
            if any(nl.get(k)!=str(v) for k,v in (pod.get("nodeSelector") or {}).items()): errs.append("nodeSelector mismatch")
            if not _node_affinity_ok(pod,nl): errs.append("required nodeAffinity mismatch")
            if any(t.get("effect") in {"NoSchedule","NoExecute"} and not _tolerates(t,pod.get("tolerations") or []) for t in spec.get("taints") or []): errs.append("untolerated NoSchedule/NoExecute taint")
            for cond in status.get("conditions") or []:
                if cond.get("type")=="Ready" and cond.get("status")!="True": errs.append("node not Ready")
            errs += _fits(req,avail.get(name,{}))
            if errs:reasons_all[name]=errs
            else:eligible.append(n)
        synthetic=[]
        for idx in range(reps):
            fits=[]
            for n in eligible:
                name=(n.get("metadata") or {}).get("name","node"); errs=_fits(req,avail[name])
                ok,aerrs=_pod_affinity_ok(pod,n,nodes,snapshot,wns,nsl,synthetic); errs += aerrs
                ok2,terrs=_topology_spread_ok(pod,n,eligible,snapshot,synthetic); errs += terrs
                if not errs:fits.append(name)
                else:reasons_all[name]=errs
            if not fits:break
            fits.sort(key=lambda n:(avail[n].get("cpu",0),avail[n].get("memory",0)),reverse=True)
            chosen=fits[0];placements.append(chosen)
            for k,v in req.items():avail[chosen][k]=avail[chosen].get(k,0)-v
            synthetic.append({"metadata":{"name":f"kubeflight-sim-{idx}","namespace":wns,"labels":labels},"spec":{"nodeName":chosen}})
        out.append(ScheduleResult(rk,reps,sorted((n.get("metadata") or {}).get("name","node") for n in eligible),placements,max(0,reps-len(placements)),reasons_all))
    return out

# ---------- cost ----------

def _cost(resources):
    cpu_rate=Decimal(os.getenv("KUBEFLIGHT_COST_CPU_MONTH", "14.60")); mem_rate=Decimal(os.getenv("KUBEFLIGHT_COST_GIB_MONTH", "1.90")); gpu_rate=Decimal(os.getenv("KUBEFLIGHT_COST_GPU_MONTH", "510")); storage_rate=Decimal(os.getenv("KUBEFLIGHT_COST_GIB_STORAGE_MONTH", "0.08")); total=Decimal(0)
    for o in resources or []:
        if o.get("kind") not in WORKLOAD_KINDS: continue
        pod,_=_pod_spec(o)
        try: req=_pod_requests(pod or {})
        except QuantityError: continue
        reps=_replicas(o); gpu=sum(v for k,v in req.items() if "gpu" in k.lower())
        total += Decimal(reps)*(Decimal(req.get("cpu",0))/1000*cpu_rate + Decimal(req.get("memory",0))/(Decimal(1024)**3)*mem_rate + Decimal(gpu)*gpu_rate)
    for o in resources or []:
        if o.get("kind")=="PersistentVolumeClaim":
            try: total += Decimal(str(gib(((((o.get("spec") or {}).get("resources") or {}).get("requests") or {}).get("storage")))))*storage_rate
            except QuantityError: pass
    return float(total)

# ---------- main ----------

def assess(resources:list[dict[str,Any]], baseline:list[dict[str,Any]]|None=None, snapshot:dict[str,Any]|None=None, target_kubernetes:str=TARGET_KUBERNETES)->Assessment:
    findings=[]; sas=set(); pds=[]; storageclasses=set()
    for o in resources:
        m=o.get("metadata") or {}; ns=m.get("namespace","default"); name=m.get("name")
        if o.get("kind")=="ServiceAccount" and name: sas.add((ns,name))
        if o.get("kind")=="PodDisruptionBudget": pds.append(o)
        if o.get("kind")=="StorageClass" and name: storageclasses.add(name)
    if snapshot:
        for sa in snapshot.get("serviceaccounts") or []:
            m=sa.get("metadata") or {}; sas.add((m.get("namespace","default"),m.get("name")))
        for sc in snapshot.get("storageclasses") or []:
            m=sc.get("metadata") or {}; storageclasses.add(m.get("name"))
    def has_pdb(w):
        wm=w.get("metadata") or {}; ns=wm.get("namespace","default"); labels=_selector_labels(w)
        for pdb in pds:
            pm=pdb.get("metadata") or {}
            if pm.get("namespace","default")!=ns: continue
            if _selector_matches((pdb.get("spec") or {}).get("selector") or {},labels): return True
        return False
    for o in resources:
        rk=resource_key(o); findings += _schema_findings(o,rk)
        if not o.get("apiVersion") or not o.get("kind") or not (o.get("metadata") or {}).get("name"): continue
        api=o.get("apiVersion")
        if api in DEPRECATED_APIS: findings.append(_finding("KF-UPG-001","critical","upgrade",f"Removed API: {api}",rk,DEPRECATED_APIS[api],"Migrate this resource to its supported stable API before deployment."))
        if o.get("kind")=="PersistentVolumeClaim":
            sc=(o.get("spec") or {}).get("storageClassName")
            if sc and snapshot is not None and sc not in storageclasses: findings.append(_finding("KF-STO-001","high","storage","StorageClass not found in target snapshot",rk,f"storageClassName={sc}","Create/select a StorageClass available in the target cluster."))
        pod,_=_pod_spec(o)
        if pod is not None:
            try: _pod_requests(pod)
            except QuantityError as e: findings.append(_finding("KF-RES-001","critical","resources","Invalid Kubernetes resource quantity",rk,str(e),"Use a valid Kubernetes Quantity; unknown quantities are never treated as zero."))
            findings += _security_findings(o,pod,rk); findings += _reliability_findings(o,pod,rk)
            sa=pod.get("serviceAccountName")
            if sa and ( (o.get("metadata") or {}).get("namespace","default"),sa) not in sas: findings.append(_finding("KF-RBAC-001","low","rbac","ServiceAccount not present in bundle or target snapshot",rk,f"serviceAccountName={sa}","Ensure the ServiceAccount exists in the target cluster or include it in the release."))
            if o.get("kind")=="Deployment" and _replicas(o)>=2 and not has_pdb(o): findings.append(_finding("KF-ROL-001","low","rollout","No matching PodDisruptionBudget found",rk,"Deployment has multiple replicas without a matching PDB in the submitted bundle","Add/verify a PodDisruptionBudget for production availability."))
    schedule=_schedule(resources,snapshot)
    for sr in schedule:
        if not sr.schedulable: findings.append(_finding("KF-SCH-001","critical","scheduling","Not all replicas can be placed",sr.workload,f"{sr.unscheduled_replicas}/{sr.replicas} replica(s) remain unscheduled; "+"; ".join(f"{n}: {','.join(r)}" for n,r in sr.reasons.items()),"Adjust requests, selectors, taints/tolerations, affinity, or cluster capacity."))
        elif len(set(sr.placements))==1 and sr.replicas>1: findings.append(_finding("KF-SCH-002","high","scheduling","All replicas collapse onto one node",sr.workload,f"All {sr.replicas} simulated replicas land on {sr.placements[0]}","Add topology spread/anti-affinity or capacity before rollout."))
    base_map={resource_key(o):o for o in (baseline or [])}; cur_map={resource_key(o):o for o in resources}; changed=[]
    if baseline is not None:
        for k in sorted(set(base_map)|set(cur_map)):
            if k not in base_map or k not in cur_map or _hash(base_map[k])!=_hash(cur_map[k]): changed.append(k)
    deps=_dependencies(resources); base_deps=_dependencies(baseline or [])
    findings += _network_policy_findings(resources,deps,snapshot); findings += _rbac_requirement_findings(resources)
    blast=_blast(changed,deps,base_deps)
    if changed and len(blast)>=3: findings.append(_finding("KF-BLAST-001","high","blast-radius","Wide dependency blast radius","ChangeSet",f"{len(blast)} dependent resources may be affected","Split the change, canary it, or add explicit rollout safeguards."))
    monthly=_cost(resources); base_cost=_cost(baseline) if baseline is not None else None
    if base_cost is not None and base_cost>0:
        ratio=monthly/base_cost
        if ratio>1.50: findings.append(_finding("KF-COST-002","high","cost","Estimated monthly cost rises >50%","ChangeSet",f"${base_cost:.2f} -> ${monthly:.2f} ({(ratio-1)*100:.1f}% increase)","Review requests/replicas or explicitly approve the budget increase."))
        elif ratio>1.10: findings.append(_finding("KF-COST-001","medium","cost","Estimated monthly cost rises >10%","ChangeSet",f"${base_cost:.2f} -> ${monthly:.2f} ({(ratio-1)*100:.1f}% increase)","Review requests/replicas or update the approved cost budget."))
    penalty=sum(SEVERITY_WEIGHT.get(f.severity,0) for f in findings); score=max(0,min(100,100-penalty)); maxsev=max((SEVERITY_WEIGHT.get(f.severity,0) for f in findings),default=0)
    decision="SAFE TO DEPLOY" if maxsev<SEVERITY_WEIGHT["high"] and score>=75 else ("REVIEW REQUIRED" if maxsev<SEVERITY_WEIGHT["critical"] and score>=50 else "DO NOT DEPLOY")
    summary={sev:sum(1 for f in findings if f.severity==sev) for sev in ["critical","high","medium","low","info"]}
    limitations=["Scheduler simulation is deterministic but not a byte-for-byte replacement for kube-scheduler plugins/admission webhooks.","Static dependency and NetworkPolicy analysis only evaluates dependencies discoverable from submitted manifests/annotations.","Provider-neutral cost estimates are directional unless rates are calibrated for your environment."]
    return Assessment(score,decision,len(resources),findings,schedule,deps,changed,blast,monthly,base_cost,target_kubernetes,summary,limitations)
