# explncc — developer and book workflows
#
# Override Python: make check PYTHON=.venv/bin/python3

PYTHON ?= python3

.PHONY: help install install-dev lint typecheck test check docs-check
.PHONY: examples examples-clean build-all-opt
.PHONY: build-inline-miss build-inline-costly build-vectorize-fail build-vectorize-success
.PHONY: build-unroll-fixed build-unroll-unknown
.PHONY: summarize-all explain-all diff-demo demo chapter11-demo chapter12-demo chapter13-demo chapter14-demo
.PHONY: chapter11 chapter11-examples chapter11-alignment chapter11-packs chapter11-dataset
.PHONY: chapter11-bench-prompts chapter11-eval-fixture chapter11-clean

help:
	@echo "explncc Makefile targets"
	@echo ""
	@echo "Python / quality:"
	@echo "  make install-dev   Install package + dev tools (editable; bootstraps pip if missing)"
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
	@echo "  make summarize-all | explain-all | diff-demo | demo | chapter11-demo | chapter12-demo | chapter13-demo | chapter14-demo"
	@echo ""
	@echo "Chapter 11 alignment pipeline (fixture-based; no Clang required):"
	@echo "  make chapter11 | chapter11-examples | chapter11-alignment | chapter11-packs"
	@echo "  make chapter11-dataset | chapter11-bench-prompts | chapter11-eval-fixture | chapter11-clean"

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

chapter11-demo: chapter11-alignment chapter11-bench-prompts
	@echo "chapter11-demo: see build/chapter11/"

CH11_BUILD := build/chapter11
CH11_ROOT := examples/chapter11_alignment
CH11_EXAMPLES := vectorized_no_alignment_claim aliasing_not_alignment cost_not_alignment aligned_intrinsic unaligned_intrinsic offset_pointer_plausible

chapter11-examples:
	@for ex in $(CH11_EXAMPLES); do \
		mkdir -p $(CH11_BUILD)/$$ex; \
		cp $(CH11_ROOT)/$$ex/fixtures/main.opt.yaml $(CH11_BUILD)/$$ex/main.opt.yaml; \
	done
	@echo "staged $(words $(CH11_EXAMPLES)) chapter 11 fixture(s) under $(CH11_BUILD)/"

chapter11-alignment: chapter11-examples
	@mkdir -p $(CH11_BUILD)/alignment
	$(EXPLNCC) alignment $(CH11_BUILD)/ --limit 20 --json > $(CH11_BUILD)/alignment/remarks.json
	@echo "wrote $(CH11_BUILD)/alignment/remarks.json"

chapter11-packs: chapter11-examples
	@mkdir -p $(CH11_BUILD)/packs
	$(EXPLNCC) alignment-pack $(CH11_BUILD)/ --format jsonl --limit 20 \
		-o $(CH11_BUILD)/packs/packs.jsonl
	$(EXPLNCC) alignment-pack $(CH11_BUILD)/aliasing_not_alignment/main.opt.yaml \
		--include-source --source-root $(CH11_ROOT)/aliasing_not_alignment \
		--format markdown -o $(CH11_BUILD)/packs/aliasing-sample.md
	@echo "wrote $(CH11_BUILD)/packs/"

chapter11-dataset: chapter11-examples
	@mkdir -p $(CH11_BUILD)/datasets
	$(EXPLNCC) dataset $(CH11_BUILD)/ --focus alignment --template guided \
		--format explncc-record -o $(CH11_BUILD)/datasets/alignment-guided.jsonl
	@echo "wrote $(CH11_BUILD)/datasets/alignment-guided.jsonl"

chapter11-bench-prompts: chapter11-examples
	@mkdir -p $(CH11_BUILD)/prompts
	$(EXPLNCC) bench-prompts $(CH11_BUILD)/ --focus alignment \
		--templates minimal,guided,rubric,adversarial,missing-context --limit 20 \
		-o $(CH11_BUILD)/prompts/bench-prompts.jsonl
	@echo "wrote $(CH11_BUILD)/prompts/bench-prompts.jsonl"

chapter11-eval-fixture: chapter11-examples
	@mkdir -p $(CH11_BUILD)/eval
	cp tests/fixtures/alignment_predictions.jsonl $(CH11_BUILD)/eval/sample-predictions.jsonl
	$(EXPLNCC) eval-alignment $(CH11_BUILD)/eval/sample-predictions.jsonl \
		--format markdown -o $(CH11_BUILD)/eval/report.md
	@echo "wrote $(CH11_BUILD)/eval/report.md"

chapter11-clean:
	rm -rf $(CH11_BUILD)

chapter11: chapter11-alignment chapter11-packs chapter11-dataset chapter11-bench-prompts chapter11-eval-fixture
	@echo "chapter 11 pipeline artifacts under $(CH11_BUILD)/"

chapter12-demo:
	$(EXPLNCC) report tests/fixtures/inline_miss_no_definition.opt.yaml \
		--format github --no-explain --top-missed 5 --title "CI sample report"

CH13_BUILD := build/chapter13

chapter13-demo:
	mkdir -p $(CH13_BUILD)
	$(EXPLNCC) trace tests/fixtures/simd_vectorized.opt.yaml --format markdown \
		--include-sample-record --include-evidence -o $(CH13_BUILD)/trace.md
	$(EXPLNCC) digest tests/fixtures/ --include-evidence | head -n 20
	$(EXPLNCC) doctor --format markdown | head -n 15
	$(EXPLNCC) report tests/fixtures/simd_vectorized.opt.yaml --format html --embed-json \
		-o $(CH13_BUILD)/report.html
	@echo "chapter 13 artifacts under $(CH13_BUILD)/"

chapter14-demo: examples
	$(EXPLNCC) viz $(EX_BUILD) --style pass-summary --format mermaid --top 10 | head -n 22

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
	@command -v $(PYTHON) >/dev/null || { echo "Python not found: $(PYTHON)"; exit 1; }
	@$(PYTHON) -c "import pip" 2>/dev/null || { \
		echo "pip missing; bootstrapping with ensurepip..."; \
		$(PYTHON) -m ensurepip --upgrade || { \
			echo "ensurepip failed. Recreate the venv, e.g.: rm -rf .venv && python3 -m venv .venv"; \
			exit 1; \
		}; \
	}
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

binary:
	$(PYTHON) -m pip install -q ".[package]"
	$(PYTHON) -m PyInstaller --onefile --name explncc --clean --noconfirm \
		--paths src --log-level WARN packaging/pyinstaller_entry.py
	./dist/explncc --version
	@echo "standalone binary: dist/explncc"

DOCS := \
	docs/README.md \
	docs/getting-started.md \
	docs/examples.md \
	docs/model-backends.md \
	docs/chapter-10-notes.md \
	docs/chapter-11-notes.md \
	docs/chapter-11-alignment.md \
	docs/chapter-12-notes.md \
	docs/chapter-12-ci.md \
	docs/chapter-13-notes.md \
	docs/architecture.md \
	docs/extending-explncc.md \
	docs/backends.md \
	docs/report-formats.md \
	docs/caching-and-digest.md \
	docs/toolchain-notes.md \
	docs/chapter-14-notes.md \
	docs/offline-first.md \
	docs/local-mode.md \
	docs/local-ranker.md \
	docs/classifier-labels.md

docs-check:
	@for f in $(DOCS); do test -f $$f || { echo "missing $$f"; exit 1; }; done
	@echo "docs OK ($(words $(DOCS)) files)"
