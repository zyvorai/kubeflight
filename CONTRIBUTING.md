# Contributing

Thanks for helping improve KubeFlight.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
bash scripts/smoke.sh
python scripts/validate_deployment.py
```

For a new check, use a stable `KF-<AREA>-NNN` rule ID, include evidence and recommendation text, and add both positive and negative tests. Avoid rules that depend on probabilistic model output.

By contributing, you agree that your contribution is licensed under Apache-2.0.
