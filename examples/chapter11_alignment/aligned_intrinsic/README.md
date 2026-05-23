# aligned_intrinsic

Uses `_mm256_load_ps` — **explicit alignment vocabulary**. Expected label: `alignment_explicit`.

The bundled fixture includes `_mm256_load_ps` in the remark text to exercise the classifier; your local Clang wording may differ — regenerate `.opt.yaml` when validating against a real build.

## Expected alignment label

`alignment_explicit`

## Compile

Requires AVX (`-mavx` or `-march=native` on capable hosts):

```bash
EX=aligned_intrinsic
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
  --include-ir --ir-file "$OUT/main.ll" \
  --include-asm --asm-file "$OUT/main.s" \
  --format markdown
```

## Fixture

```bash
python -m explncc alignment fixtures/main.opt.yaml --json
```
