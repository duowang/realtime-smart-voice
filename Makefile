.PHONY: setup run dev-deps lint test check

setup:
	./run.sh --setup-only

run:
	./run.sh

dev-deps:
	. venv/bin/activate && python -m pip install -r requirements-dev.txt

lint:
	. venv/bin/activate && ruff check src

test:
	. venv/bin/activate && pytest

check:
	. venv/bin/activate && python -m compileall src && ruff check src && pytest
