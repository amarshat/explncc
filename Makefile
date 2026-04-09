.PHONY: install check

PYTHON ?= python3

install:
	$(PYTHON) -m pip install -e ".[dev]"

check:
	$(PYTHON) -m ruff check src tests
	$(PYTHON) -m ruff format --check src tests
	$(PYTHON) -m mypy src
	$(PYTHON) -m pytest -q
