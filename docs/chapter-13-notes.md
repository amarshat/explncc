# Notes for Chapter 13 (architecture + shipping the companion CLI)

**Primary documentation:** [architecture.md](architecture.md) — full pipeline, trust model, module map.

Chapter outline: *Inside explncc: From Optimization Logs to Compiler-Semantic Infrastructure* — deterministic reduction layer with optional model backends.

## Core invariant (say this early)

**Only explanation backends are nondeterministic.** Parse → normalize → analyze → report must be reproducible, testable, cacheable, and CI-safe.

## What explncc adds for this chapter

| Heading | Reader learns to DO | explncc support |
|---------|---------------------|-----------------|
| **Architecture** | Trace `.opt.yaml` → records → artifacts | `explncc trace` |
| **Stable identity** | Cache and diff reliably | `record_id`, `record_hash`, `evidence_hash` |
| **Evidence packs** | Model-facing unit, not raw YAML | `explncc evidence`, `EvidencePack` |
| **Backends** | Configure rule / remote / auto safely | `explain`, `doctor`, [backends.md](backends.md) |
| **Caching** | Key CI on remark files | `digest --include-evidence`, [caching-and-digest.md](caching-and-digest.md) |
| **Reports** | Pick format by consumer | [report-formats.md](report-formats.md) |
| **Extending** | Add backend, format, check | [extending-explncc.md](extending-explncc.md) |
| **Toolchains** | Clang today; generalize later | `toolchains/`, [toolchain-notes.md](toolchain-notes.md) |

## Example commands

```bash
python -m explncc trace build/examples/vectorize_success/ --format markdown -o trace.md
python -m explncc digest build/examples/ --include-evidence
python -m explncc doctor --format markdown
python -m explncc report build/app.opt.yaml --format html --embed-json -o report.html
python -m explncc explain build/app.opt.yaml --backend auto
```

## Repository samples

- `examples/chapter13_architecture/README.md` — copy-paste demo workflow
- `make chapter13` — fixture-based smoke (after `make install-dev`)

## Module map (thin CLI)

`cli.py` orchestrates; logic lives in modules — see [architecture.md](architecture.md).

## Sidebar: GCC / MSVC

Clang `.opt.yaml` is the native input. GCC/MSVC need different adapters — documented, not implemented. See [toolchain-notes.md](toolchain-notes.md).
