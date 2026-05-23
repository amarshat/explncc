# unaligned_intrinsic

Uses `_mm256_loadu_ps` — **explicit unaligned access** in source. Expected label: `alignment_explicit` (the remark mentions alignment vocabulary; unaligned access may be intentional, not a defect).

## Expected alignment label

`alignment_explicit`

## Compile

```bash
EX=unaligned_intrinsic
ROOT=examples/chapter11_alignment/$EX
OUT=build/chapter11/$EX
mkdir -p "$OUT"

clang++ -std=c++17 -O3 -march=native -Wall -Wextra -mavx \
  -fsave-optimization-record \
  -foptimization-record-file="$OUT/main.opt.yaml" \
  "$ROOT/main.cpp" -o "$OUT/main"

clang++ -std=c++17 -O3 -march=native -mavx -S -emit-llvm "$ROOT/main.cpp" -o "$OUT/main.ll"
clang++ -std=c++17 -O3 -march=native -mavx -S "$ROOT/main.cpp" -o "$OUT/main.s"
```

## explncc

```bash
python -m explncc alignment-pack "$OUT/main.opt.yaml" \
  --include-source --source-root "$ROOT" \
  --format markdown
```

## Fixture

```bash
python -m explncc alignment fixtures/main.opt.yaml --json
```
