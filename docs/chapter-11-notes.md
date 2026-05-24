# Notes for Chapter 11 (alignment / SIMD + LLM training)

**Primary documentation:** [chapter-11-alignment.md](chapter-11-alignment.md) — full alignment evidence pipeline guide (labels, packs, datasets, bench-prompts, evaluator, Make targets, limitations).

**LST background:** [chapter-10-notes.md](chapter-10-notes.md) — Lossless Semantic Tree and evidence packs.

This file is a compact companion for authors already familiar with explncc Chapter 11 work.

## Quick demo

```bash
make install-dev
make chapter11                    # full fixture pipeline → build/chapter11/
python -m explncc alignment build/chapter11/ --limit 20 --json
```

## What changed in the alignment pipeline

1. **Classification** — `explncc alignment` adds `alignment_label`, confidence, reasons, missing context.
2. **Evidence packs** — `explncc alignment-pack` with optional source/IR/assembly.
3. **Examples** — `examples/chapter11_alignment/` (six cases + fixture `.opt.yaml`).
4. **Dataset** — `dataset --focus alignment` with conservative teachers and labeled rows.
5. **Bench-prompts** — `minimal`, `guided`, `rubric`, `adversarial`, `missing-context` + overreach traps.
6. **Evaluator** — `eval-alignment` heuristic scoring (no LLM judge).

## Test one command

```bash
pytest tests/test_chapter11_pipeline.py -q   # Make-equivalent smoke tests
pytest tests/test_alignment*.py tests/test_chapter11_examples.py -q
```

## IR reminder

IR is not in `.opt.yaml`. Join externally or use `alignment-pack --include-ir`.
