# Getting started with explncc

This guide assumes macOS with [Homebrew](https://brew.sh/) and Python 3.12+.

## 1. Install LLVM (Clang with optimization remarks)

```bash
brew install llvm
```

Use the Homebrew LLVM `clang++` for consistent remark output. The top-level `Makefile` tries to resolve `$(brew --prefix llvm)/bin/clang++`; override with `LLVM_BIN=/path/to/clang++` if needed.

## 2. Create a Python environment and install explncc

```bash
cd /path/to/explncc
python3.12 -m venv .venv
source .venv/bin/activate
make install-dev
```

## 3. Build the book examples and emit `.opt.yaml`

```bash
make examples
```

Artifacts land under `build/examples/<example-name>/` (binary plus `.opt.yaml`).

## 4. Run explncc

```bash
explncc summary build/examples/vectorize_aliasing_fail/
explncc stats build/examples/unroll_fixed_trip/
explncc explain build/examples/inline_too_costly/ --backend rule
```

## 5. Optional: local model via Ollama

Install [Ollama](https://ollama.com/), pull a model (see [model-backends.md](model-backends.md)), then:

```bash
explncc explain build/examples/vectorize_aliasing_fail/ --backend ollama
```

## 6. Run tests

```bash
make test
```

For a full developer gate (lint, format check, types, tests):

```bash
make check
```
