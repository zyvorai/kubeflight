# Copyright 2026 Zyvor AI Labs · https://zyvor.dev
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from pathlib import Path
from typing import Any, Iterable
import shutil, subprocess, tempfile
import yaml

SUPPORTED_EXTENSIONS={".yaml",".yml",".json"}
class ManifestError(ValueError): pass

def _flatten(doc:Any)->Iterable[dict[str,Any]]:
    if doc is None:return
    if not isinstance(doc,dict): raise ManifestError("Each YAML document must be a Kubernetes object")
    if doc.get("kind")=="List" and isinstance(doc.get("items"),list):
        for item in doc["items"]:
            if isinstance(item,dict): yield item
        return
    yield doc

def parse_text(text:str,source:str="input")->list[dict[str,Any]]:
    try:
        out=[]
        for doc in yaml.safe_load_all(text): out.extend(_flatten(doc) or [])
        return out
    except yaml.YAMLError as exc: raise ManifestError(f"Invalid YAML in {source}: {exc}") from exc

def _run(args:list[str],cwd:Path)->str:
    try:return subprocess.check_output(args,cwd=cwd,text=True,stderr=subprocess.STDOUT,timeout=45)
    except FileNotFoundError as exc: raise ManifestError(f"Required renderer not installed: {args[0]}") from exc
    except subprocess.CalledProcessError as exc: raise ManifestError(f"Renderer failed: {' '.join(args)}\n{exc.output}") from exc
    except subprocess.TimeoutExpired as exc: raise ManifestError(f"Renderer timed out: {' '.join(args)}") from exc

def load_path(path:str|Path,*,render:bool=True)->list[dict[str,Any]]:
    p=Path(path)
    if not p.exists(): raise ManifestError(f"Path does not exist: {p}")
    if p.is_dir() and render:
        if (p/"Chart.yaml").exists(): return parse_text(_run(["helm","template","kubeflight-input","."],p),str(p))
        if (p/"kustomization.yaml").exists() or (p/"kustomization.yml").exists():
            if shutil.which("kubectl"): text=_run(["kubectl","kustomize","."],p)
            else: text=_run(["kustomize","build","."],p)
            return parse_text(text,str(p))
    files=[p] if p.is_file() else sorted(x for x in p.rglob("*") if x.suffix.lower() in SUPPORTED_EXTENSIONS and ".github" not in x.parts and "node_modules" not in x.parts and ".venv" not in x.parts)
    if not files: raise ManifestError(f"No YAML/JSON manifests found under {p}")
    out=[]
    for f in files: out.extend(parse_text(f.read_text(encoding="utf-8"),str(f)))
    return out

def autodetect_path(root:str|Path=".")->Path:
    root=Path(root)
    for rel in ("deploy/kubernetes","k8s","kubernetes","manifests","deploy","charts"):
        p=root/rel
        if p.exists():
            if p.name=="charts":
                charts=[x for x in p.iterdir() if x.is_dir() and (x/"Chart.yaml").exists()]
                if len(charts)==1:return charts[0]
            else:return p
    if (root/"Chart.yaml").exists() or (root/"kustomization.yaml").exists():return root
    return root

def resource_key(obj:dict[str,Any])->str:
    m=obj.get("metadata") or {}; return f"{obj.get('kind','Unknown')}/{m.get('namespace','default')}/{m.get('name','unnamed')}"
