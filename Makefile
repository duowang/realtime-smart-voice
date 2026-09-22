.PHONY: setup run dev-deps lint test check benchmark

setup:
	./run.sh --setup-only

run:
	./run.sh

dev-deps:
	. venv/bin/activate && python -m pip install -r requirements-dev.txt

lint:
	. venv/bin/activate && ruff check src tests generate_audio.py

test:
	. venv/bin/activate && pytest

check:
	. venv/bin/activate && python -m compileall -q src tests generate_audio.py && ruff check src tests generate_audio.py && pytest

benchmark:
	venv/bin/python tests/performance_sweep.py --output tmp/performance-sweep/current.json
