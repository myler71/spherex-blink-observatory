.PHONY: setup test test-live lint format typecheck run precache benchmarks coverage

PYTHON := .venv/bin/python
PYTEST := .venv/bin/pytest
RUFF := .venv/bin/ruff
MYPY := .venv/bin/mypy
UVICORN := .venv/bin/uvicorn

setup:
	uv venv --python 3.11 .venv
	uv pip install --python .venv/bin/python -r backend/requirements.lock.txt

test:
	PYTHONPATH=backend $(PYTEST) -m "not live" -q

test-live:
	PYTHONPATH=backend $(PYTEST) -m "live" -v

coverage:
	PYTHONPATH=backend $(PYTEST) -m "not live" --cov=app.science --cov=app.narrator.validator --cov-report=term-missing

lint:
	$(RUFF) check backend

format:
	$(RUFF) format --check backend

typecheck:
	$(MYPY) backend/app

run:
	PYTHONPATH=backend $(UVICORN) app.main:app --host 0.0.0.0 --port 8000

precache:
	PYTHONPATH=backend $(PYTHON) -m app.jobs.precache

benchmarks:
	PYTHONPATH=backend $(PYTHON) -m app.jobs.run_benchmarks
