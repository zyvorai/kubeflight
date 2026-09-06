# Copyright 2026 Zyvor AI Labs · https://zyvor.dev
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import argparse,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
from . import __version__
from .cluster import in_cluster_snapshot,load_snapshot,ClusterError
from .engine import assess
from .parser import load_path,autodetect_path,ManifestError
from .report import text_report,json_report,html_report,markdown_report,sarif_report


def _server_dry_run(path:str)->tuple[bool,str]:
    if not shutil.which("kubectl"): return False,"kubectl is not installed"
    try:
        p=subprocess.run(["kubectl","apply","--dry-run=server","-f",path],text=True,capture_output=True,timeout=60)
        return p.returncode==0,(p.stdout+p.stderr).strip()
    except Exception as e:return False,str(e)

def main(argv=None):
    p=argparse.ArgumentParser(prog="kubeflight",description="Kubernetes deployment preflight simulator — know what may break before you deploy.")
    p.add_argument("--version",action="version",version=f"kubeflight {__version__}")
    sub=p.add_subparsers(dest="cmd",required=True)
    for name,helptext in (("check","Analyze Kubernetes manifests"),("plan","Auto-detect and analyze this repository's Kubernetes deployment")):
        c=sub.add_parser(name,help=helptext)
        if name=="check":c.add_argument("path")
        else:c.add_argument("path",nargs="?",default=".")
        c.add_argument("--baseline");c.add_argument("--cluster-snapshot");c.add_argument("--in-cluster",action="store_true")
        c.add_argument("--format",choices=["text","json","html","markdown","sarif"],default="text");c.add_argument("--output");c.add_argument("--fail-on",choices=["never","high","critical"],default="critical");c.add_argument("--server-dry-run",action="store_true")
    s=sub.add_parser("serve",help="Run the KubeFlight dashboard/API");s.add_argument("--host",default="0.0.0.0");s.add_argument("--port",type=int,default=8080)
    a=p.parse_args(argv)
    if a.cmd=="serve":
        import uvicorn;uvicorn.run("kubeflight.server:app",host=a.host,port=a.port,log_level="info");return 0
    try:
        path=autodetect_path(a.path) if a.cmd=="plan" else Path(a.path)
        resources=load_path(path);baseline=load_path(a.baseline) if a.baseline else None
        snapshot=load_snapshot(a.cluster_snapshot) if a.cluster_snapshot else (in_cluster_snapshot() if a.in_cluster else None)
        result=assess(resources,baseline,snapshot)
        if a.server_dry_run:
            ok,msg=_server_dry_run(str(path))
            if not ok:
                print(f"kubeflight: server dry-run failed/unavailable: {msg}",file=sys.stderr)
                return 4
    except (ManifestError,ClusterError,ValueError,json.JSONDecodeError) as e:
        print(f"kubeflight: {e}",file=sys.stderr);return 2
    renderer={"text":text_report,"json":json_report,"html":html_report,"markdown":markdown_report,"sarif":sarif_report}[a.format]
    out=renderer(result)
    if a.output:Path(a.output).write_text(out,encoding="utf-8")
    else:print(out,end="")
    sev={f.severity for f in result.findings}
    if a.fail_on=="critical" and "critical" in sev:return 3
    if a.fail_on=="high" and ({"critical","high"}&sev):return 3
    return 0

if __name__=="__main__":raise SystemExit(main())
