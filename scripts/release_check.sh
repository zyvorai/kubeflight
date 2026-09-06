#!/usr/bin/env bash
# Copyright 2026 Zyvor AI Labs · https://zyvor.dev
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
echo '[1/7] compile'; python -m compileall -q kubeflight tests
echo '[2/7] tests'; PYTHONPATH=. pytest -q
echo '[3/7] API smoke'; bash scripts/smoke.sh
echo '[4/7] Kubernetes self-analysis'; PYTHONPATH=. python scripts/validate_deployment.py
echo '[5/7] YAML metadata validation'; python - <<'PY'
from pathlib import Path
import yaml
for p in [Path('action.yml'),Path('charts/kubeflight/Chart.yaml'),Path('charts/kubeflight/values.yaml'),*Path('.github/workflows').glob('*.yml')]:
    with p.open() as f: yaml.safe_load(f)
    print('yaml:',p,'PASS')
PY
echo '[6/7] wheel build'; rm -rf build dist *.egg-info; python -m pip wheel . --no-deps --no-build-isolation -w dist >/tmp/kubeflight-wheel.log; ls -lh dist/kubeflight-0.2.0-py3-none-any.whl
echo '[7/7] installed package smoke'; tmp="$(mktemp -d)"; python -m pip install --no-deps --target "$tmp/site" dist/kubeflight-0.2.0-py3-none-any.whl >/dev/null; printf 'apiVersion: v1\nkind: ConfigMap\nmetadata: {name: wheel-smoke}\n' > "$tmp/x.yaml"; PYTHONPATH="$tmp/site" python -m kubeflight.cli check "$tmp/x.yaml" --format json --fail-on never > "$tmp/out.json"; python -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["resources"]==1' "$tmp/out.json"; rm -rf "$tmp"
echo 'release checks: PASS'
