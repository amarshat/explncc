# explncc — developer and book workflows
#
# Override Python: make check PYTHON=.venv/bin/python3

PYTHON ?= python3

.PHONY: help install install-dev lint typecheck test check docs-check

help:
	@echo "explncc Makefile targets"
	@echo ""
	@echo "  make install-dev   Install package + dev tools (editable)"
	@echo "  make lint          Ruff lint"
	@echo "  make typecheck     Mypy on src/"
	@echo "  make test          Pytest"
	@echo "  make check         lint + format check + typecheck + test"
	@echo "  make docs-check    Verify documentation files exist"
	@echo ""
	@echo "Example and demo targets are added once sources are present:"
	@echo "  make examples, build-all-opt, summarize-all, explain-all, diff-demo, demo"

install: install-dev

install-dev:
	$(PYTHON) -m pip install -e ".[dev,ai]"

lint:
	$(PYTHON) -m ruff check src tests

fmt-check:
	$(PYTHON) -m ruff format --check src tests

typecheck:
	$(PYTHON) -m mypy src

test:
	$(PYTHON) -m pytest -q

check: lint fmt-check typecheck test

DOCS := \
	docs/README.md \
	docs/getting-started.md \
	docs/examples.md \
	docs/model-backends.md \
	docs/chapter-10-notes.md

docs-check:
	@for f in $(DOCS); do test -f $$f || { echo "missing $$f"; exit 1; }; done
	@echo "docs OK ($(words $(DOCS)) files)"
