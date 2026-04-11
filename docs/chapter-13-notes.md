# Notes for Chapter 13 (architecture + shipping the companion CLI)

Chapter outline: *Inside explncc: From optimization logs to insight and CI artifacts* — how modules connect, configuring rule / Ollama / OpenAI / Claude, cache keys and masked config, HTML alongside Markdown/JSON/PR reports, and treating the CLI as a thin layer over small packages. Intermediate → advanced (~12–14 pages). Earlier chapters already show *what* to run; this chapter is *why it is shaped this way* and *how to extend it safely*.

## What explncc adds for this chapter

| Heading | Reader learns to DO | explncc support |
|---------|---------------------|-----------------|
| **Architecture (log → insight → artifact)** | Trace data from `.opt.yaml` through parse/normalize to reports; see where nondeterminism appears (optional models only). | `parser` → `normalizer` → `OptimizationRecord` → `stats` / `diffing` / `checks` (deterministic); `explain` adds rule text then optional HTTP backends; `ci_report` builds artifacts. |
| **Configuring prompt backends** | Set env vars; pick `rule`, `ollama`, `openai`, `claude`, or `auto` for laptop vs CI. | `explain` / `report --explain-backend …`; see [model-backends.md](model-backends.md). `auto`: try Ollama, then Claude if `ANTHROPIC_API_KEY` set, then OpenAI if `OPENAI_API_KEY` set. |
| **Local vs remote / caching** | Key CI steps on unchanged optimization logs; debug backends without leaking secrets. | `explncc digest` — per-file `sha256`, `record_count`, aggregate `cache_key`. `explncc doctor` — masked JSON (`set`/`unset` for API keys). |
| **Markdown, HTML, JSON, terminal** | Choose format per consumer (wiki, PR bot, dashboard, browser). | `report --format markdown\|json\|github\|html`; HTML uses escaped strings for safe standalone pages. |
| **Packaging the companion tool** | Install editable, run quality gates; map book sections to single files. | `make install-dev`, `make check`; Typer entry in `cli.py`; small modules per concern (see below). |

## Trust and limitations (say this in prose)

- **Compiler YAML is authoritative**; digests hash *files* — if two builds produce byte-identical `.opt.yaml` but different binaries, the digest still matches; use digests for “did the remark *file* change?” not full build identity.
- **Model backends** receive grounded JSON slices; failures fall back to rule-only text where implemented.
- **Secrets**: never log raw keys; `doctor` is for masked status only — still avoid pasting into public issues if your policy forbids even `set`/`unset`.
- **Other toolchains**: `explncc` targets Clang `.opt.yaml`; GCC/MSVC paths differ (sidebar).

## Example commands (copy into the book)

```bash
# Aggregate digest over all *.opt.yaml under a tree (CI cache key input)
python -m explncc digest build/

# Masked backend-related config (support / CI logs)
python -m explncc doctor

# Self-contained HTML report (browser or attachment)
python -m explncc report build/app.opt.yaml --format html --no-explain -o report.html

# Claude backend (requires ANTHROPIC_API_KEY)
python -m explncc explain build/examples/inline_miss_no_definition/main.opt.yaml --backend claude
```

## Repository / module map

- `src/explncc/parser.py`, `normalizer.py`, `models.py` — stream parse → stable records
- `src/explncc/explain/backends.py` — rule + Ollama + OpenAI + Claude + `auto`
- `src/explncc/ci_report.py` — Markdown, JSON, GitHub-flavored, HTML
- `src/explncc/digest.py`, `config.py` — `digest` / `doctor`
- `src/explncc/cli.py` — Typer commands

## Skills ↔ chapter outcomes

1. **Explain the pipeline** — inputs, deterministic core, optional LLM, outputs.
2. **Configure backends** — env vars; `auto` ordering; when to use `--no-explain` in CI (Chapter 12 overlap).
3. **Stabilize CI** — `digest` for cache keys; `doctor` for triage without key leakage.
4. **Pick report formats** — Markdown vs `github` vs JSON vs HTML by audience.
5. **Ship maintainably** — thin CLI, one module per chapter hook, `make check` before releases.

## Sidebar: GCC / MSVC CLI utilities

While Clang offers detailed `-Rpass`, `.opt.yaml`, and IR dumps, **GCC** often surfaces optimization via **`-fdump-tree-*`**, **`-fopt-info`**, and similar text — parsing those needs different tooling (e.g. opt-diff, custom tree-dump parsers) than this repo’s YAML path. **MSVC** integrates with **Visual Studio Diagnostic Tools**; **`/FA`** assembly output is a common manual path for performance introspection. A “companion” for those stacks would mirror *their* artifacts, not `.opt.yaml`.
