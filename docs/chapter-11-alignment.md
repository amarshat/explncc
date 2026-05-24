# Chapter 11 — Alignment evidence pipeline

*Training an LLM to diagnose memory misalignment (SSE/AVX)* — dataset design, fine-tuning vs instruction tuning, and evaluation.

## Thesis

**Alignment is a systems fact.** A model can only reason about it when given grounded compiler evidence, source context, optional IR, optional assembly, and strict uncertainty rules.

**explncc does not train models.** It builds reproducible, inspectable evidence and evaluation artifacts for your downstream pipeline.

## Pipeline

```
source
  → compiler
  → .opt.yaml / IR / assembly
  → explncc alignment / alignment-pack
  → dataset / bench-prompts
  → model (external)
  → eval-alignment
```

This extends the Chapter 10 **Lossless Semantic Tree (LST)** workflow: the same evidence-pack tree (compiler remark → normalized record → pack → optional context leaves), plus alignment classification nodes and evaluation artifacts.

See [chapter-10-notes.md](chapter-10-notes.md) for the LST definition and teaching order.

## LST in Chapter 11

Chapter 11 does not replace the LST — it **annotates** it:

```text
.opt.yaml remark
  └── OptimizationRecord
        └── AlignmentEvidencePack
              ├── compiler fields (pass, kind, message, costs, …)
              ├── alignment_label + confidence + evidence_reasons
              ├── related_records[]
              └── optional context leaves (source / IR / asm)
```

Alignment labels are **heuristic**, not ground truth. Teachers and `eval-alignment` enforce conservative language (“plausible, not proven”) unless evidence is explicit.

## Commands overview

| Step | Command |
|------|---------|
| Heuristic slice + labels | `explncc alignment` |
| Evidence packs | `explncc alignment-pack` |
| Training JSONL | `explncc dataset --focus alignment` |
| Prompt benchmarks | `explncc bench-prompts --focus alignment` |
| Score model outputs | `explncc eval-alignment` |

### One-shot Make workflow

```bash
make chapter11-examples      # stage fixture .opt.yaml under build/chapter11/
make chapter11-alignment     # classification JSON
make chapter11-packs         # evidence packs JSONL + sample markdown
make chapter11-dataset       # guided dataset JSONL
make chapter11-bench-prompts # bench fixtures with overreach traps
make chapter11-eval-fixture  # sample predictions + eval report
make chapter11-clean         # remove build/chapter11/
```

Or run the full pipeline: `make chapter11`

## Alignment evidence labels

Each remark in the alignment slice receives a **heuristic** label (not ground truth):

| Label | Meaning |
|-------|---------|
| `alignment_explicit` | Remark text mentions alignment vocabulary (`assume_aligned`, `_mm256_load_ps`, misaligned, etc.). |
| `alignment_plausible_not_proven` | SIMD/vectorization involved; alignment not proven by the remark alone. Successful vectorization with `vectorization_factor` usually lands here. |
| `alignment_unlikely_from_evidence` | Remark points to aliasing, cost, no definition, call-in-loop, unsupported op, reduction, etc. |
| `insufficient_evidence` | Heuristic match but sparse remark text. |
| `not_alignment_related` | No SIMD/vectorization/alignment heuristic signals. |

**SIMD relevance alone is not alignment evidence.** Never treat heuristic labels as oracle ground truth.

### Classification output fields

`explncc alignment --json` adds:

- `alignment_label`, `alignment_confidence` (`low` \| `medium` \| `high`)
- `evidence_reasons`, `missing_context`, `recommended_next_steps`
- `alignment_signals` (why the remark entered the slice)

## Alignment evidence packs

```bash
python -m explncc alignment-pack examples/chapter11_alignment/ \
  --format jsonl -o packs.jsonl

python -m explncc alignment-pack examples/chapter11_alignment/aliasing_not_alignment/fixtures/main.opt.yaml \
  --include-source --source-root examples/chapter11_alignment/aliasing_not_alignment \
  --include-ir --ir-file tests/fixtures/t.ll \
  --include-asm --asm-file tests/fixtures/t.s \
  --format markdown
```

Pack fields include compiler vocabulary (`pass_name`, `kind`, `message`, costs, target when present), classification fields, snippet slots, `assembly_signals` (conservative mnemonic hints), `pack_id`, `raw_record_hash`.

Unavailable fields stay `null`; gaps are listed in `missing_context`. explncc never invents compiler facts.

## Source, IR, and assembly attachment

| Flag | Purpose |
|------|---------|
| `--include-source --source-root PATH` | Window around DebugLoc (`--context-before 5`, `--context-after 8`) |
| `--include-ir --ir-file FILE.ll` | Bounded `define` slice (`--ir-lines 50`) |
| `--include-asm --asm-file FILE.s` | Function label slice (`--asm-lines 60`) + mnemonic scan |

Assembly signals (`vmovups`, `movaps`, …) add conservative `evidence_reasons` — e.g. “contains unaligned vector move mnemonic vmovups”, **not** “program has an alignment bug”.

The same attachment logic applies to `explncc evidence`.

## Chapter 11 examples

Six case studies under `examples/chapter11_alignment/`:

| Example | Expected label |
|---------|----------------|
| `vectorized_no_alignment_claim` | `alignment_plausible_not_proven` |
| `aliasing_not_alignment` | `alignment_unlikely_from_evidence` |
| `cost_not_alignment` | `alignment_unlikely_from_evidence` |
| `aligned_intrinsic` | `alignment_explicit` |
| `unaligned_intrinsic` | `alignment_explicit` |
| `offset_pointer_plausible` | `alignment_plausible_not_proven` |

Each has `main.cpp`, `README.md`, and `fixtures/main.opt.yaml` for CI without Clang. Regenerate `.opt.yaml` locally when validating against a specific Clang version.

## Dataset generation

```bash
python -m explncc dataset examples/chapter11_alignment/ \
  --focus alignment \
  --template guided \
  --format explncc-record \
  -o build/chapter11/datasets/alignment-guided.jsonl
```

Row schema (`--focus alignment`):

- `sample_id`, `evidence`, `source_context`, `ir_context`, `assembly_context`
- `alignment_label`, `alignment_confidence`, `evidence_reasons`, `missing_context`
- `teacher_response`, `expected_behavior`, `task`, `constraints`

Formats: `explncc-record`, `openai-messages`, `chatml`, `plain-prompt-completion`, `legacy-prompt-completion`.

**Teachers are conservative** — they do not claim alignment as root cause unless `alignment_label` is `alignment_explicit`.

Example teacher (plausible, not proven):

> The compiler record confirms SIMD/vectorization involvement, but it does not explicitly mention alignment. Alignment may affect performance in principle, but this evidence alone does not prove a misalignment issue. Inspect allocation guarantees, pointer arithmetic, IR alignment metadata, or assembly load/store forms next.

## Bench-prompt fixtures

```bash
python -m explncc bench-prompts examples/chapter11_alignment/ \
  --focus alignment \
  --templates minimal,guided,rubric,adversarial,missing-context \
  --limit 20 \
  -o build/chapter11/prompts/bench-prompts.jsonl
```

| Variant | Purpose |
|---------|---------|
| `minimal` | Direct question |
| `guided` | Sectioned answer structure |
| `rubric` | Self-scoring rubric line |
| `adversarial` | Leading “alignment bug” wording — good models resist |
| `missing-context` | No source/IR/asm/target — must list missing evidence |

Each row: `sample_id`, `variant`, `prompt`, `expected_alignment_label`, `expected_good_behavior`, `overreach_traps`.

## Evaluate model outputs

```bash
python -m explncc eval-alignment build/chapter11/eval/sample-predictions.jsonl \
  --format markdown \
  --output build/chapter11/eval/report.md
```

Input JSONL: `sample_id`, `model_output`, `expected_alignment_label`, plus optional `evidence`, `missing_context`, `overreach_traps`.

| Dimension | Range |
|-----------|-------|
| evidence_fidelity | 0–2 |
| alignment_discipline | 0–2 |
| missing_context_awareness | 0–2 |
| next_step_quality | 0–2 |
| overreach_penalty | 0 to −3 |
| conciseness | 0–1 |

Heuristic overreach flags include: “definitely alignment”, AVX2 without target evidence, misalignment claims on weak labels, “alignment bug” on sparse evidence, invented vector width.

## IR in the loop

Clang IR is **not** embedded in `.opt.yaml`. Generate IR/assembly externally (`clang -emit-llvm -S`, `clang -S`) and join via `alignment-pack --include-ir/--include-asm` or your own `(file, line)` keys.

## Limitations (state in the book)

- Heuristic `alignment` retrieval is **not proof** — can miss or include irrelevant remarks.
- Classification labels and rule teachers are **heuristics**, not oracle labels.
- `.opt.yaml` may omit alignment-specific detail even when alignment matters in source.
- IR/assembly joins can be wrong if DebugLoc keys or paths are sloppy.
- Provider fine-tuning formats change — validate JSONL against your API spec.
- AI usage is **optional and downstream** — explncc never calls model APIs in its core path.

## Testing

```bash
make test
pytest tests/test_alignment.py tests/test_alignment_pack.py tests/test_alignment_dataset.py \
  tests/test_alignment_bench.py tests/test_alignment_eval.py tests/test_chapter11_examples.py \
  tests/test_chapter11_pipeline.py -q
```

## Book mapping

| Chapter heading | explncc hooks |
|-----------------|---------------|
| Why alignment matters | Raw `.opt.yaml` → `alignment --json` → `explain --backend rule` |
| SSE/AVX case studies | `examples/chapter11_alignment/` + `make chapter11` |
| Prompt–completion datasets | `dataset --focus alignment --format explncc-record` |
| Fine-tuning vs instruction tuning | Same JSONL; pick `openai-messages` or `chatml` for your provider |
| Prompt benchmarks | `bench-prompts` + `eval-alignment` |

See also [chapter-11-notes.md](chapter-11-notes.md) for a shorter changelog-oriented companion.
