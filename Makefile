# explncc — developer and book workflows
#
# Override Python: make check PYTHON=.venv/bin/python3

PYTHON ?= python3

.PHONY: help install install-dev lint typecheck test check docs-check
.PHONY: examples examples-clean build-all-opt
.PHONY: build-inline-miss build-inline-costly build-vectorize-fail build-vectorize-success
.PHONY: build-unroll-fixed build-unroll-unknown
.PHONY: summarize-all explain-all diff-demo demo chapter11-demo chapter12-demo

help:
	@echo "explncc Makefile targets"
	@echo ""
	@echo "Python / quality:"
	@echo "  make install-dev   Install package + dev tools (editable)"
	@echo "  make lint          Ruff lint"
	@echo "  make typecheck     Mypy on src/"
	@echo "  make test          Pytest"
	@echo "  make check         lint + format check + typecheck + test"
	@echo "  make docs-check    Verify documentation files exist"
	@echo ""
	@echo "Clang examples (require LLVM clang++ — see docs/getting-started.md):"
	@echo "  make examples | build-all-opt"
	@echo "  make build-inline-miss | build-inline-costly | build-vectorize-fail | ..."
	@echo "  make examples-clean"
	@echo ""
	@echo "explncc demos (after install-dev + examples):"
	@echo "  make summarize-all | explain-all | diff-demo | demo | chapter11-demo | chapter12-demo"

UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
  HOMEBREW_LLVM_PREFIX := $(shell brew --prefix llvm 2>/dev/null)
  ifneq ($(HOMEBREW_LLVM_PREFIX),)
    DEFAULT_CLANGXX := $(HOMEBREW_LLVM_PREFIX)/bin/clang++
  else
    DEFAULT_CLANGXX := clang++
  endif
else
  DEFAULT_CLANGXX := clang++
endif

LLVM_BIN ?= $(DEFAULT_CLANGXX)
CXX := $(LLVM_BIN)

EX_BUILD := build/examples

# Override e.g. MARCH=generic if -march=native is undesirable on your host.
MARCH ?= native
CXXFLAGS_EX := -std=c++17 -O3 -march=$(MARCH) -Wall -Wextra -Wpedantic -fsave-optimization-record

INLINE_MISS_BIN := $(EX_BUILD)/inline_miss_no_definition/inline_miss_demo
INLINE_BEFORE := $(EX_BUILD)/inline_too_costly/before/before
INLINE_AFTER := $(EX_BUILD)/inline_too_costly/after/after
VEC_FAIL := $(EX_BUILD)/vectorize_aliasing_fail/vectorize_fail
VEC_OK := $(EX_BUILD)/vectorize_success/vectorize_success
UNROLL_FIXED := $(EX_BUILD)/unroll_fixed_trip/unroll_fixed
UNROLL_UNKNOWN := $(EX_BUILD)/unroll_unknown_trip/unroll_unknown

build-inline-miss: $(INLINE_MISS_BIN)
build-inline-costly: $(INLINE_BEFORE) $(INLINE_AFTER)
build-vectorize-fail: $(VEC_FAIL)
build-vectorize-success: $(VEC_OK)
build-unroll-fixed: $(UNROLL_FIXED)
build-unroll-unknown: $(UNROLL_UNKNOWN)

build-all-opt: $(INLINE_MISS_BIN) $(INLINE_BEFORE) $(INLINE_AFTER) $(VEC_FAIL) $(VEC_OK) $(UNROLL_FIXED) $(UNROLL_UNKNOWN)

examples: build-all-opt

examples-clean:
	rm -rf $(EX_BUILD)

EXPLNCC := $(PYTHON) -m explncc

summarize-all: examples
	$(EXPLNCC) summary $(EX_BUILD) --limit 40

explain-all: examples
	$(EXPLNCC) explain $(EX_BUILD)/vectorize_aliasing_fail/vectorize_fail.opt.yaml --backend rule --limit 25

diff-demo: examples
	$(EXPLNCC) diff $(EX_BUILD)/inline_too_costly/before/before.opt.yaml $(EX_BUILD)/inline_too_costly/after/after.opt.yaml

demo: summarize-all diff-demo

chapter11-demo: examples
	$(EXPLNCC) alignment $(EX_BUILD)/vectorize_success/ --limit 15
	$(EXPLNCC) bench-prompts $(EX_BUILD)/vectorize_success/vectorize_success.opt.yaml \
		--focus alignment --templates minimal,guided --limit 3 | head -n 2

chapter12-demo:
	$(EXPLNCC) report tests/fixtures/inline_miss_no_definition.opt.yaml \
		--format github --no-explain --top-missed 5 --title "CI sample report"

$(EX_BUILD)/inline_miss_no_definition/main.o: examples/inline_miss_no_definition/main.cpp
	mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS_EX) -foptimization-record-file=$(EX_BUILD)/inline_miss_no_definition/main.opt.yaml -c $< -o $@

$(EX_BUILD)/inline_miss_no_definition/callee.o: examples/inline_miss_no_definition/callee.cpp
	mkdir -p $(dir $@)
	$(CXX) -std=c++17 -O3 -march=$(MARCH) -Wall -Wextra -Wpedantic -c $< -o $@

$(INLINE_MISS_BIN): $(EX_BUILD)/inline_miss_no_definition/main.o $(EX_BUILD)/inline_miss_no_definition/callee.o
	mkdir -p $(dir $@)
	$(CXX) -std=c++17 -O3 -march=$(MARCH) $^ -o $@

$(INLINE_BEFORE): examples/inline_too_costly/before/before.cpp
	mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS_EX) -foptimization-record-file=$(EX_BUILD)/inline_too_costly/before/before.opt.yaml $< -o $@

$(INLINE_AFTER): examples/inline_too_costly/after/after.cpp
	mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS_EX) -foptimization-record-file=$(EX_BUILD)/inline_too_costly/after/after.opt.yaml $< -o $@

$(VEC_FAIL): examples/vectorize_aliasing_fail/main.cpp
	mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS_EX) -foptimization-record-file=$(EX_BUILD)/vectorize_aliasing_fail/vectorize_fail.opt.yaml $< -o $@

$(VEC_OK): examples/vectorize_success/main.cpp
	mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS_EX) -foptimization-record-file=$(EX_BUILD)/vectorize_success/vectorize_success.opt.yaml $< -o $@

$(UNROLL_FIXED): examples/unroll_fixed_trip/main.cpp
	mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS_EX) -foptimization-record-file=$(EX_BUILD)/unroll_fixed_trip/unroll_fixed.opt.yaml $< -o $@

$(UNROLL_UNKNOWN): examples/unroll_unknown_trip/main.cpp
	mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS_EX) -foptimization-record-file=$(EX_BUILD)/unroll_unknown_trip/unroll_unknown.opt.yaml $< -o $@

install: install-dev

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

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
	docs/chapter-10-notes.md \
	docs/chapter-11-notes.md \
	docs/chapter-12-notes.md

docs-check:
	@for f in $(DOCS); do test -f $$f || { echo "missing $$f"; exit 1; }; done
	@echo "docs OK ($(words $(DOCS)) files)"
