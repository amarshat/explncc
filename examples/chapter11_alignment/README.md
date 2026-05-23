# Chapter 11 alignment examples

Small C++ programs for the alignment evidence pipeline. Each directory teaches one **expected alignment label** when run through `explncc alignment` / `explncc alignment-pack`.

| Directory | Expected label | Story |
|-----------|----------------|-------|
| `vectorized_no_alignment_claim/` | `alignment_plausible_not_proven` | Successful vectorization without explicit alignment vocabulary in the remark |
| `aliasing_not_alignment/` | `alignment_unlikely_from_evidence` | Missed vectorization due to memory independence / aliasing |
| `cost_not_alignment/` | `alignment_unlikely_from_evidence` | Missed vectorization due to cost / profitability |
| `aligned_intrinsic/` | `alignment_explicit` | Source uses `_mm256_load_ps` (aligned intrinsic) |
| `unaligned_intrinsic/` | `alignment_explicit` | Source uses `_mm256_loadu_ps` (intentional unaligned access) |
| `offset_pointer_plausible/` | `alignment_plausible_not_proven` | Pointer offset (`input + 1`) — layout may matter, remark does not prove misalignment |

## Fixture-first workflow (CI / no Clang)

Each example ships `fixtures/main.opt.yaml` — representative compiler remarks for tests and book demos without rebuilding:

```bash
python -m explncc alignment examples/chapter11_alignment/vectorized_no_alignment_claim/fixtures/main.opt.yaml --json
python -m explncc alignment-pack examples/chapter11_alignment/ --format jsonl --limit 20
```

## Full compile workflow (local Clang with optimization records)

From the repo root (requires LLVM `clang++` with `-fsave-optimization-record`):

```bash
make chapter11-examples   # when Makefile target is available
# or per-example README compile blocks
```

Generated artifacts (typical layout):

```
build/chapter11/<example>/main.opt.yaml
build/chapter11/<example>/main.ll
build/chapter11/<example>/main.s
```

## explncc alignment-pack demo

```bash
python -m explncc alignment-pack examples/chapter11_alignment/aliasing_not_alignment/fixtures/main.opt.yaml \
  --include-source --source-root examples/chapter11_alignment/aliasing_not_alignment \
  --format markdown
```

**Note:** Hand-crafted fixtures are **teaching aids**, not ground truth from your compiler. Regenerate `.opt.yaml` locally when validating against a specific Clang version.
