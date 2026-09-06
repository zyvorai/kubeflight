.PHONY: install test check smoke serve report package deploy-remote smoke-remote
install:
	python -m pip install -e .
test:
	PYTHONPATH=. pytest -q
check:
	python -m compileall -q kubeflight tests
	PYTHONPATH=. pytest -q
smoke:
	bash scripts/smoke.sh
serve:
	PYTHONPATH=. python -m kubeflight.cli serve --host 0.0.0.0 --port 8080
report:
	PYTHONPATH=. python -m kubeflight.cli check examples/demo/app.yaml --baseline examples/demo/baseline.yaml --cluster-snapshot examples/demo/cluster-snapshot.json --format html --output report.html --fail-on never
package:
	python -m build

deploy-remote:
	bash scripts/deploy-remote.sh $(ARGS)

smoke-remote:
	bash scripts/smoke-remote.sh