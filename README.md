# explncc

**Explain Compiler** — a CLI for parsing, summarizing, and diffing Clang/LLVM optimization remark logs (`.opt.yaml`).

Companion tooling for the book *Decode the Compiler: AI-Guided Explanations of C/C++ Optimization Logs for Real-World Performance*.

> This repository is under active construction. Installable package skeleton, linting, and type-checking are in place; commands and documentation expand in subsequent milestones.

## Install (editable)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Documentation layout

- `docs/getting-started.md` — LLVM install, editable install, running tests
- `docs/examples.md` — what each `examples/*` program demonstrates
- `docs/model-backends.md` — rule / Ollama / OpenAI and environment variables
- `docs/chapter-10-notes.md` — suggested book pacing

## Verify

```bash
make docs-check
make check
explncc --version
explncc --help
```

## License

MIT
