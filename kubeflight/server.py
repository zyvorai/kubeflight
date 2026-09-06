# Copyright 2026 Zyvor AI Labs · https://zyvor.dev
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import asyncio,hmac,json,os,time
from collections import defaultdict,deque
from pathlib import Path
from typing import Any
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import HTMLResponse,JSONResponse
from pydantic import BaseModel,Field
from . import __version__
from .cluster import in_cluster_snapshot,ClusterError
from .engine import assess
from .parser import parse_text,ManifestError

WEB=Path(__file__).with_name("web")
app=FastAPI(title="KubeFlight",version=__version__,docs_url="/api/docs",redoc_url=None)
MAX_BODY=int(os.getenv("KUBEFLIGHT_MAX_BODY_BYTES","4194304"));MAX_CONCURRENT=int(os.getenv("KUBEFLIGHT_MAX_CONCURRENT","8"));RATE=int(os.getenv("KUBEFLIGHT_RATE_PER_MINUTE","60"));SEM=asyncio.Semaphore(MAX_CONCURRENT);HITS=defaultdict(deque)

def _auth_ok(request:Request)->bool:
    expected=os.getenv("KUBEFLIGHT_API_TOKEN","")
    if not expected:return True
    auth=request.headers.get("authorization","")
    got=auth[7:] if auth.lower().startswith("bearer ") else ""
    return hmac.compare_digest(got.encode(),expected.encode())

@app.middleware("http")
async def guard(request:Request,call_next):
    cl=request.headers.get("content-length")
    if cl:
        try:
            if int(cl)>MAX_BODY:return JSONResponse({"detail":"request body too large"},status_code=413)
        except ValueError:return JSONResponse({"detail":"invalid Content-Length"},status_code=400)
    ip=request.client.host if request.client else "unknown";now=time.time();q=HITS[ip]
    while q and q[0]<now-60:q.popleft()
    if len(q)>=RATE:return JSONResponse({"detail":"rate limit exceeded"},status_code=429)
    q.append(now)
    async with SEM:return await call_next(request)

class CheckRequest(BaseModel):
    manifests:str=Field(min_length=1,max_length=MAX_BODY)
    baseline:str|None=Field(default=None,max_length=MAX_BODY)
    snapshot:dict[str,Any]|None=None
    use_in_cluster:bool=False

@app.get("/",response_class=HTMLResponse)
def home():return (WEB/"index.html").read_text(encoding="utf-8")
@app.get("/api/healthz")
def healthz():return {"status":"ok","version":__version__}
@app.get("/api/readyz")
def readyz():return {"status":"ready"}
@app.get("/api/demo")
def demo():return {"manifests":(WEB/"demo-app.yaml").read_text(),"baseline":(WEB/"demo-baseline.yaml").read_text(),"snapshot":json.loads((WEB/"demo-cluster-snapshot.json").read_text())}
@app.post("/api/check")
def check(req:CheckRequest,request:Request):
    if not _auth_ok(request):raise HTTPException(401,"invalid bearer token")
    try:
        resources=parse_text(req.manifests);baseline=parse_text(req.baseline) if req.baseline else None;snapshot=req.snapshot
        if req.use_in_cluster:
            if os.getenv("KUBEFLIGHT_LIVE_CLUSTER","false").lower() not in {"1","true","yes"}:raise HTTPException(403,"live-cluster access is disabled; set KUBEFLIGHT_LIVE_CLUSTER=true explicitly")
            if not os.getenv("KUBEFLIGHT_API_TOKEN"):raise HTTPException(403,"live-cluster access requires KUBEFLIGHT_API_TOKEN")
            snapshot=in_cluster_snapshot()
        return assess(resources,baseline,snapshot).to_dict()
    except HTTPException:raise
    except (ManifestError,ClusterError,ValueError) as e:raise HTTPException(400,str(e)) from e
