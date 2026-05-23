# Notes for Chapter 11 (alignment / SIMD + LLM training)

Chapter outline: *Training an LLM to diagnose memory misalignment (SSE/AVX)* — dataset design, fine-tuning vs instruction tuning, and evaluation.

## Thesis

Alignment is a **systems fact**. A model can only reason about it when given grounded compiler evidence, source context, optional IR, optional assembly, and strict uncertainty rules. explncc does **not** train models; it builds reproducible, inspectable evidence and evaluation artifacts.

## How explncc supports this chapter (objectively)

explncc gives you **deterministic** building blocks:

1. **A reproducible slice of compiler remarks** that often co-occur with SIMD and alignment discussions (`explncc alignment`). The signals are **heuristics** (pass names, substrings, `vectorization_factor`); they are useful for filtering, not ground truth.
2. **Alignment evidence classification** on each sliced remark — explicit labels, confidence, reasons, missing context, and recommended next steps (also heuristic, not oracle labels).
3. **Prompt–completion JSONL** derived from normalized remarks plus optional rule-based “teacher” text (`explncc dataset`). You can swap the teacher for human labels, larger models, or IR-augmented prompts in your own pipeline.
4. **Prompt A/B fixtures** as JSONL (`explncc bench-prompts`) so you can run the same records through multiple prompt shapes and compare model outputs offline.

## Alignment evidence labels

Each remark in the alignment slice can be classified into one of:

| Label | Meaning |
|-------|---------|
| `alignment_explicit` | Remark text directly mentions alignment vocabulary (aligned load/store, `assume_aligned`, `_mm256_load_ps`, misaligned, etc.). |
| `alignment_plausible_not_proven` | SIMD/vectorization is involved; memory layout may matter, but the remark does not prove alignment is the issue. Successful vectorization with `vectorization_factor` usually lands here unless explicit alignment evidence exists. |
| `alignment_unlikely_from_evidence` | Remark points to another cause: aliasing, cost rejection, no definition, call in loop, unsupported operation, reduction, etc. |
| `insufficient_evidence` | Heuristic slice matched but text is too sparse to classify alignment relevance. |
| `not_alignment_related` | Record does not match SIMD/vectorization/alignment heuristics at all. |

**Important:** SIMD relevance alone is **not** alignment evidence. Do not treat heuristic labels as ground truth.

## Mapping to main headings

| Chapter heading | explncc hooks |
|-----------------|---------------|
| Why alignment matters in vectorization | Teach from raw `.opt.yaml`, then `alignment --json` + `explain --backend rule` on vector passes. |
| Case study setup (SSE/AVX edge failures) | `make examples`; compare aliasing vs success cases; `diff` optional. |
| Constructing a prompt–completion dataset | `dataset --focus alignment --template guided --format explncc-record`; add IR in a separate column/tool. |
| Fine-tuning vs instruction tuning | Same JSONL works for both: use `openai-messages` for chat fine-tuning APIs; use `explncc-record` when you need metadata for papers. |
| Prompt quality benchmarks | `bench-prompts --templates minimal,guided,rubric,adversarial,missing-context` then score responses in your evaluator. |

## Alignment evidence packs (milestone 2)

Build deterministic, inspectable evidence packs from the alignment slice:

```bash
# JSON to stdout
python -m explncc alignment-pack tests/fixtures/simd_vectorized.opt.yaml --format json

# JSONL to file
python -m explncc alignment-pack tests/fixtures/simd_vectorized.opt.yaml \
  --format jsonl -o /tmp/packs.jsonl

# Markdown (screenshot-friendly)
python -m explncc alignment-pack tests/fixtures/simd_vectorized.opt.yaml --format markdown

# Filter by classification label
python -m explncc alignment-pack tests/fixtures/simd_vectorized.opt.yaml \
  --label alignment_plausible_not_proven
```

Each pack includes compiler fields (pass, kind, message, costs, target when present), alignment classification from milestone 1, `missing_context`, and stable `pack_id` / `raw_record_hash` references.

### Attach source, IR, and assembly (milestone 3)

Fixtures under `tests/fixtures/` (`t.cpp`, `t.ll`, `t.s`) pair with `simd_vectorized.opt.yaml` (`DebugLoc: t.cpp:2`, function `_Z3foov`):

```bash
python -m explncc alignment-pack tests/fixtures/simd_vectorized.opt.yaml \
  --include-source --source-root tests/fixtures \
  --include-ir --ir-file tests/fixtures/t.ll \
  --include-asm --asm-file tests/fixtures/t.s \
  --format markdown
```

When a snippet cannot be resolved, the field stays `null` and remains in `missing_context`. Assembly mnemonics (`vmovups`, `movaps`, etc.) are reported conservatively under `assembly_signals` and `evidence_reasons` — not as proof of a bug.

The same attachment logic is shared with `explncc evidence --include-source ...`.

Run snippet tests:

```bash
pytest tests/test_context_snippets.py tests/test_alignment_pack.py::test_pack_with_context_attachment -q
```

## Testing milestone 1 (alignment classification)

From the repo root:

```bash
# Install dev deps if needed
make install-dev

# Unit + CLI tests for classification
pytest tests/test_alignment.py tests/test_cli.py::test_alignment_json_includes_signals -q

# Full test suite
make test

# Inspect classification on the SIMD fixture
python -m explncc alignment tests/fixtures/simd_vectorized.opt.yaml --json

# Table view shows label + confidence columns
python -m explncc alignment tests/fixtures/simd_vectorized.opt.yaml
```

Expected on `simd_vectorized.opt.yaml`:

- `alignment_label`: `alignment_plausible_not_proven`
- `alignment_confidence`: `medium`
- `missing_context` includes `source_snippet`, `ir_snippet`, `assembly_snippet`, `target_triple`

Try synthetic cases in a Python shell:

```python
from explncc.alignment import classify_alignment
from explncc.models import OptimizationRecord

# Aliasing miss → unlikely from alignment evidence
classify_alignment(OptimizationRecord(
    kind="missed", pass_name="loop-vectorize", remark_name="MissedDetails",
    message="cannot prove memory independence",
)).alignment_label  # alignment_unlikely_from_evidence

# Explicit intrinsic → alignment_explicit
classify_alignment(OptimizationRecord(
    kind="passed", pass_name="loop-vectorize", remark_name="Vectorized",
    message="uses _mm256_load_ps", vectorization_factor=8,
)).alignment_label  # alignment_explicit
```

## IR in the loop

Clang IR is **not** embedded in `.opt.yaml`. For “remark + IR + response” rows, keep IR generation outside explncc (e.g. `clang -emit-llvm -S`) and join on `(file, line)` or your own build IDs. explncc `metadata` fields are there to anchor that join.

## Limitations (state these in the book)

- Heuristic `alignment` slice can **miss** subtle remarks or **include** irrelevant ones.
- Classification labels are **heuristic**, not ground truth — never fine-tune on them as oracle labels without human review.
- Rule-based teachers are **short** and generic; they are baselines, not oracle labels.
- Model APIs and fine-tuning formats change; validate JSONL against your provider’s current spec.

## Pipeline (upcoming milestones)

```
source → compiler → .opt.yaml / IR / assembly
  → explncc alignment / alignment-pack
  → dataset / bench-prompts
  → model (external)
  → eval-alignment
```

Milestone 1 adds classification to `explncc alignment`. Milestone 2 adds `explncc alignment-pack`. Milestone 3 adds source/IR/assembly attachment. Milestone 4 adds `examples/chapter11_alignment/` with six case studies and fixture `.opt.yaml` files. Milestone 5 extends `explncc dataset --focus alignment` with labeled rows and conservative teachers. Milestone 6 extends `bench-prompts` with adversarial and missing-context variants plus overreach traps. Later milestones add evaluator, Make targets, and full test coverage.

## Chapter 11 examples (milestone 4)

Six teaching cases under `examples/chapter11_alignment/`:

| Example | Expected label |
|---------|----------------|
| `vectorized_no_alignment_claim` | `alignment_plausible_not_proven` |
| `aliasing_not_alignment` | `alignment_unlikely_from_evidence` |
| `cost_not_alignment` | `alignment_unlikely_from_evidence` |
| `aligned_intrinsic` | `alignment_explicit` |
| `unaligned_intrinsic` | `alignment_explicit` |
| `offset_pointer_plausible` | `alignment_plausible_not_proven` |

Each directory has `main.cpp`, `README.md` (compile / IR / asm / alignment-pack commands), and `fixtures/main.opt.yaml` for CI without Clang.

```bash
# Classify all fixture remarks
python -m explncc alignment examples/chapter11_alignment/ --json

# Pack with source for aliasing case
python -m explncc alignment-pack \
  examples/chapter11_alignment/aliasing_not_alignment/fixtures/main.opt.yaml \
  --include-source --source-root examples/chapter11_alignment/aliasing_not_alignment \
  --format markdown

pytest tests/test_chapter11_examples.py -q
```

## Alignment dataset rows (milestone 5)

With `--focus alignment`, `explncc dataset` emits rows with explicit labels and conservative rule-based teachers:

```bash
python -m explncc dataset examples/chapter11_alignment/ \
  --focus alignment \
  --template guided \
  --format explncc-record \
  -o /tmp/alignment-guided.jsonl

python -m explncc dataset examples/chapter11_alignment/aliasing_not_alignment/fixtures/main.opt.yaml \
  --focus alignment --format openai-messages --template minimal \
  -o /tmp/alignment-openai.jsonl
```

Each row includes: `sample_id`, `evidence`, `source_context`, `ir_context`, `assembly_context`, `alignment_label`, `alignment_confidence`, `evidence_reasons`, `missing_context`, `teacher_response`, `expected_behavior`, plus `task` and `constraints`.

Formats for `--focus alignment`: `explncc-record`, `openai-messages`, `chatml`, `plain-prompt-completion`, `legacy-prompt-completion`.

Teachers are **conservative** — they do not claim alignment as root cause unless `alignment_label` is `alignment_explicit`. Optional `--include-source`, `--include-ir`, and `--include-asm` match `alignment-pack`.

```bash
pytest tests/test_alignment_dataset.py -q
```

## Bench-prompt variants (milestone 6)

With `--focus alignment`, `bench-prompts` emits evaluation fixtures with traps:

```bash
python -m explncc bench-prompts examples/chapter11_alignment/ \
  --focus alignment \
  --templates minimal,guided,rubric,adversarial,missing-context \
  --limit 20 \
  -o /tmp/bench-prompts.jsonl
```

Each line includes: `sample_id`, `variant`, `prompt`, `expected_alignment_label`, `expected_good_behavior`, `overreach_traps`.

| Variant | Purpose |
|---------|---------|
| `minimal` | Direct question, limited structure |
| `guided` | Sectioned answer (claim, SIMD, alignment evidence, next step) |
| `rubric` | Self-scoring rubric line |
| `adversarial` | Leading question tempting overclaim (“alignment bug”, “confirm misalignment”) |
| `missing-context` | No source/IR/asm/target — model must list missing evidence |

```bash
pytest tests/test_alignment_bench.py -q
```
