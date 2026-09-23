.PHONY: setup run doctor dev-deps security-deps audit lint test check benchmark

setup:
	./run.sh --setup-only

run:
	./run.sh

doctor:
	./run.sh --doctor

dev-deps:
	. venv/bin/activate && python -m pip install -r requirements-dev.txt

security-deps:
	venv/bin/python -m pip install -r requirements-security.txt

audit:
	venv/bin/python -m pip_audit --progress-spinner off
	venv/bin/python -m bandit -r src -ll

lint:
	. venv/bin/activate && ruff check src tests

test:
	. venv/bin/activate && pytest

check:
	. venv/bin/activate && python -m compileall -q src tests && ruff check src tests && pytest

benchmark:
	venv/bin/python tests/performance_sweep.py --output tmp/performance-sweep/current.json
