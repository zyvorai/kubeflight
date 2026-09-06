#!/usr/bin/env bash
# Copyright 2026 Zyvor AI Labs
# SPDX-License-Identifier: Apache-2.0
# ============================================================================
# smoke-remote.sh — Verify a running KubeFlight instance (local or remote)
# ============================================================================
# Checks healthz, dashboard HTML, demo API, and a /api/check round-trip.
#
# Usage:
#   ./scripts/smoke-remote.sh
#   KUBEFLIGHT_URL=http://212.8.248.187:27754 ./scripts/smoke-remote.sh
#
set -euo pipefail

BASE="${KUBEFLIGHT_URL:-http://127.0.0.1:8080}"
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
