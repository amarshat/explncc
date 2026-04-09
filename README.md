# explncc

**Explain Compiler** — parse Clang/LLVM `.opt.yaml` optimization remark streams, normalize them into a stable schema, and drive **summary**, **stats**, **diff**, **export**, **check**, and **explain** workflows from the terminal.

Companion tooling for *Decode the Compiler: AI-Guided Explanations of C/C++ Optimization Logs for Real-World Performance*.

## Why optimization logs matter

The compiler already decided what to optimize, what to skip, and often *why*. Those decisions are recorded as YAML streams with tags such as `!Missed`, `!Passed`, and `!Analysis`. Treating that output as data — rather than scrolling thousands of lines by hand — is what makes performance work reproducible and teachable.

## Why `.opt.yaml`

Clang can emit a machine-oriented record of optimization events tied to source locations. explncc:

- parses YAML **document streams** (not a single mapping),
- preserves remark **kind** from YAML tags,
- normalizes inconsistent `Args` into `message`, `cost`, `threshold`, and related fields **without inventing data**,
- supports **directory** inputs (all `*.opt.yaml` recursively).

## Install

```bash
python3.12 -m venv .venv
source .venv/bin/activate
make install-dev
```

## Quick start

```bash
make examples
python -m explncc summary build/examples/ --limit 20
python -m explncc stats build/examples/vectorize_aliasing_fail/ --json
python -m explncc diff \
  build/examples/inline_too_costly/before/before.opt.yaml \
  build/examples/inline_too_costly/after/after.opt.yaml
python -m explncc explain build/examples/inline_miss_no_definition/main.opt.yaml --backend rule
python -m explncc export build/examples/ --format jsonl -o /tmp/out.jsonl
python -m explncc check build/examples/ --max-missed-inline 200
```

## Example output (summary)

Rich tables list `kind`, `pass`, `remark`, `function`, location, and a truncated `message`. Use `--json` or `--jsonl` for stable downstream tooling.

## Architecture

| Module | Role |
|--------|------|
| `explncc/parser.py` | YAML stream loader with `!Missed` / `!Passed` / `!Analysis` |
| `explncc/normalizer.py` | Raw document → `OptimizationRecord` |
| `explncc/models.py` | Pydantic schema |
| `explncc/summary.py` / `stats.py` | Filtering and aggregates |
| `explncc/diffing.py` | Build-vs-build missed deltas and counters |
| `explncc/exporters.py` | `json`, `jsonl`, `csv` |
| `explncc/checks.py` | CI thresholds |
| `explncc/explain/` | Rule text + optional HTTP backends |
| `explncc/cli.py` | Typer commands |

Subpackages stay small so a book chapter can point to one file at a time.

## Supported inputs

- Clang/LLVM `-fsave-optimization-record` / `-foptimization-record-file=…` output (`.opt.yaml`)
- One file or a directory tree; only `*.opt.yaml` files are read

## Limitations

- Heuristics depend on Clang’s YAML shape; newer LLVM versions may add fields (handled conservatively).
- **Diff** compares fingerprints of normalized rows; identical logical events with different wording may look distinct.
- **AI backends** augment text only; they never replace normalized records.

## Roadmap

- Deeper remark-specific extractors (more structured fields from `Args`)
- Optional SARIF or LSP-adjacent bridges
- Tighter CI recipes (`explncc check` presets)

## For readers of *Decode the Compiler*

Use the bundled `examples/` to emit real `.opt.yaml` on your machine, then run explncc to connect source patterns to compiler vocabulary. See `docs/chapter-10-notes.md` for a suggested teaching order.

## Why not just read `.opt.yaml` manually?

You can — and you should, once — to see the raw stream. explncc exists so you can **filter**, **count**, **diff across builds**, and **export** the same information reliably for notes, CI, and (optionally) model-assisted prose.

## Design principles

1. **Deterministic core first** — every command works without network access.
2. **No invented fields** — missing data stays absent; `args_raw` preserves the source.
3. **AI as augmentation** — rule text is always available; HTTP backends only enrich.

## Optional model backends

- **Ollama** (local): set `OLLAMA_HOST`, `OLLAMA_MODEL` (default `qwen2.5-coder:7b-instruct`).
- **OpenAI**: set `OPENAI_API_KEY`; optional `OPENAI_MODEL` (default `gpt-4o-mini`).

See [docs/model-backends.md](docs/model-backends.md).

## Building the book examples

```bash
brew install llvm   # macOS
make examples       # writes under build/examples/<name>/
```

Details: [docs/getting-started.md](docs/getting-started.md) and [docs/examples.md](docs/examples.md).

## Contributing

- `make check` — ruff, format check, mypy, pytest
- `make docs-check` — required doc files present
- Prefer focused changes with tests beside `tests/fixtures/*.opt.yaml`

## Development workflow

```bash
make install-dev
make check
make demo          # needs `make examples` first
```

## License

MIT
