#!/usr/bin/env bash
# Copyright 2026 Zyvor AI Labs
# SPDX-License-Identifier: Apache-2.0
# ============================================================================
# smoke-remote.sh — Verify a running KubeFlight instance (local or remote)
# ============================================================================
# Checks healthz, dashboard HTML, demo API, and a /api/check round-trip.
#
# Usage:
#   KUBEFLIGHT_URL=http://212.8.248.187:27754 ./scripts/smoke-remote.sh
#   ./scripts/smoke-remote.sh --port 27754
#   KUBEFLIGHT_PORT=27754 ./scripts/smoke-remote.sh
#   ./scripts/smoke-remote.sh   # uses HOST:PORT from .deploy-last
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT_FROM_CLI=""
while [ $# -gt 0 ]; do
  case "$1" in
    --port) [ $# -ge 2 ] || { echo "--port requires a value" >&2; exit 2; }; PORT_FROM_CLI="$2"; shift 2 ;;
    --port=*) PORT_FROM_CLI="${1#*=}"; shift ;;
    --help|-h)
      sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

BASE="${KUBEFLIGHT_URL:-}"
HOST_FROM_LAST=""
PORT_FROM_LAST=""
if [ -f "$ROOT/.deploy-last" ]; then
  # shellcheck disable=SC1091
  source "$ROOT/.deploy-last"
  HOST_FROM_LAST="${HOST:-}"
  PORT_FROM_LAST="${PORT:-}"
fi

if [ -z "$BASE" ]; then
  PORT_RESOLVED="${PORT_FROM_CLI:-${KUBEFLIGHT_PORT:-$PORT_FROM_LAST}}"
  HOST_RESOLVED="${KUBEFLIGHT_HOST:-$HOST_FROM_LAST}"
  if [ -n "$HOST_RESOLVED" ] && [ -n "$PORT_RESOLVED" ]; then
    BASE="http://${HOST_RESOLVED}:${PORT_RESOLVED}"
  fi
fi
[ -n "$BASE" ] || {
  echo "Set KUBEFLIGHT_URL=http://host:port, or --port / KUBEFLIGHT_PORT with host from .deploy-last" >&2
  exit 2
}
BASE="${BASE%/}"
TMPDIR_SMOKE="${TMPDIR:-/tmp}"

pass() { printf '  ✅ %s\n' "$*"; }
fail() { printf '  ❌ %s\n' "$*" >&2; exit 1; }

echo "KubeFlight smoke → ${BASE}"

code="$(curl -sS -o "${TMPDIR_SMOKE}/kubeflight-smoke-health.json" -w '%{http_code}' "${BASE}/api/healthz")"
[ "$code" = "200" ] || fail "healthz HTTP ${code}"
grep -q '"status":"ok"' "${TMPDIR_SMOKE}/kubeflight-smoke-health.json" || fail "healthz body missing status=ok"
pass "healthz"

code="$(curl -sS -o "${TMPDIR_SMOKE}/kubeflight-smoke-dash.html" -w '%{http_code}' "${BASE}/")"
[ "$code" = "200" ] || fail "dashboard HTTP ${code}"
grep -qi 'Know what will break\|KubeFlight\|html' "${TMPDIR_SMOKE}/kubeflight-smoke-dash.html" || fail "dashboard body unexpected"
pass "dashboard"

code="$(curl -sS -o "${TMPDIR_SMOKE}/kubeflight-smoke-demo.json" -w '%{http_code}' "${BASE}/api/demo")"
[ "$code" = "200" ] || fail "demo HTTP ${code}"
grep -q 'manifests\|baseline\|snapshot' "${TMPDIR_SMOKE}/kubeflight-smoke-demo.json" || fail "demo payload unexpected"
pass "demo"

python3 - <<PY
import json, urllib.request, sys
base = "${BASE}"
demo = json.load(urllib.request.urlopen(base + "/api/demo"))
req = urllib.request.Request(
    base + "/api/check",
    data=json.dumps(demo).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
r = json.load(urllib.request.urlopen(req))
assert "score" in r and "decision" in r, r
assert 0 <= int(r["score"]) <= 100, r
print("  ✅ check → score", r["score"], r["decision"])
PY

echo "  ✨ smoke OK"
