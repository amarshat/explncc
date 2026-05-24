# Notes for Chapter 10 (progressive tool use + LST)

Chapter 10: *Prompt Engineering for Compiler Logs: Structure, Context, and Constraints*.

## Thesis

The compiler already performed the hard semantic reasoning. Tooling must **preserve, reduce, and expose** that reasoning cleanly — not ask an LLM to guess from raw source.

This is the **Lossless Semantic Tree (LST)** workflow:

```text
.opt.yaml → normalized record → evidence pack → prompt template → optional model explanation
```

## What is LST?

**LST = Lossless Semantic Tree.**

| Term | Meaning |
|------|---------|
| **Lossless** | Facts come from the compiler record; nothing is invented. Missing fields stay absent; `missing_context` lists gaps. |
| **Semantic** | Pass, kind, remark, message, costs, vectorization factor, DebugLoc — optimization *decisions*, not prose summaries. |
| **Tree** | One primary remark as root, `related_records[]` as linked siblings (same function / log), optional context leaves (source, IR, assembly). |

```text
.opt.yaml remark
  └── OptimizationRecord
        └── EvidencePack
              ├── primary fields + pack_id
              ├── related_records[]
              └── source_snippet / ir_snippet / assembly_snippet (optional)
```

IR and assembly are **not** embedded in `.opt.yaml`. Generate them with Clang (`-emit-llvm`, `-S`) and attach via `evidence --include-ir` / `--include-asm`.

## Suggested teaching order

1. **Emit remarks** — `clang++` with `-fsave-optimization-record` and `-foptimization-record-file=`. Use `make examples` for a shared layout under `build/examples/`.
2. **Read structure** — YAML stream, `!Missed` / `!Passed` / `!Analysis`, variable `Args`. Motivate normalization (`explncc export`).
3. **Summarize** — `explncc summary` and `explncc stats` to collapse volume into pass/function/kind counts.
4. **Build evidence packs** — `explncc evidence` (JSONL for pipelines). Show `pack_id`, `related_records`, `missing_context`.
5. **Attach context** — `--include-source --source-root`, optional `--include-ir`, `--include-asm`. Emphasize: context leaves are optional; the remark node is authoritative.
6. **Compare builds** — `explncc diff` on before/after pairs; tie to CI with `explncc check`.
7. **Interpret** — `explncc explain --backend rule` on **records or packs**, not raw YAML; optional `ollama` / `openai` once the deterministic story is clear.

## Example commands

```bash
# One pack per remark
python -m explncc evidence build/examples/inline_miss_no_definition/main.opt.yaml \
  --format jsonl -o /tmp/packs.jsonl

# LST with source leaf
python -m explncc evidence build/examples/vectorize_success/main.opt.yaml \
  --include-source --source-root examples/vectorize_success \
  --format markdown -o /tmp/pack.md

# Prompt row from a pack (Chapter 10 → 11 bridge)
python -m explncc dataset build/examples/vectorize_aliasing_fail/ \
  --template guided --format explncc-record -o /tmp/rows.jsonl
```

## What to say in prose

- **Not** “paste `.opt.yaml` into ChatGPT.”
- **Do** “build a minimal evidence pack, attach only the context you have, then prompt with constraints.”
- **`pack_id`** is a deterministic hash — useful for caching and deduplication in training pipelines.

## Later chapters

- **Chapter 11** — `alignment-pack` extends the LST with alignment labels and conservative teachers.
- **Chapter 12** — `report` summarizes LST roots at CI scale; `report-diff` compares LST snapshots across builds.

This order keeps the **deterministic core** authoritative; AI appears as an optional layer without hiding the compiler’s vocabulary.
