#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT="${PORT:-18080}"
PYTHONPATH=. python -m kubeflight.cli serve --host 127.0.0.1 --port "$PORT" >/tmp/kubeflight-smoke.log 2>&1 &
pid=$!
trap 'kill "$pid" 2>/dev/null || true' EXIT
for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:$PORT/api/healthz" >/dev/null 2>&1; then break; fi
  sleep .1
done
curl -fsS "http://127.0.0.1:$PORT/api/healthz" | grep -q '"status":"ok"'
curl -fsS "http://127.0.0.1:$PORT/" | grep -q 'Know what will break'
python - <<PY
import json, urllib.request
base='http://127.0.0.1:$PORT'
d=json.load(urllib.request.urlopen(base+'/api/demo'))
req=urllib.request.Request(base+'/api/check',data=json.dumps(d).encode(),headers={'Content-Type':'application/json'},method='POST')
r=json.load(urllib.request.urlopen(req))
assert r['score'] == 84, r
assert r['decision'] == 'REVIEW REQUIRED', r
print('smoke: API + demo preflight PASS (84/100 REVIEW REQUIRED)')
PY
