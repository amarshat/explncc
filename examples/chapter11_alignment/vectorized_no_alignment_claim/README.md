# vectorized_no_alignment_claim

Successful loop vectorization. The compiler remark confirms SIMD involvement but **does not explicitly claim alignment** as the reason — the expected label is `alignment_plausible_not_proven`.

## Expected alignment label

`alignment_plausible_not_proven`

## Compile (generate `.opt.yaml`, IR, assembly)

From the repo root:

```bash
EX=vectorized_no_alignment_claim
ROOT=examples/chapter11_alignment/$EX
OUT=build/chapter11/$EX
mkdir -p "$OUT"

clang++ -std=c++17 -O3 -march=native -Wall -Wextra \
  -fsave-optimization-record \
  -foptimization-record-file="$OUT/main.opt.yaml" \
  "$ROOT/main.cpp" -o "$OUT/main"

clang++ -std=c++17 -O3 -march=native -S -emit-llvm "$ROOT/main.cpp" -o "$OUT/main.ll"
clang++ -std=c++17 -O3 -march=native -S "$ROOT/main.cpp" -o "$OUT/main.s"
```

## explncc

```bash
python -m explncc alignment "$OUT/main.opt.yaml" --json

python -m explncc alignment-pack "$OUT/main.opt.yaml" \
  --include-source --source-root "$ROOT" \
  --include-ir --ir-file "$OUT/main.ll" \
  --include-asm --asm-file "$OUT/main.s" \
  --format markdown
```

## Fixture (CI)

```bash
python -m explncc alignment fixtures/main.opt.yaml --json
```
