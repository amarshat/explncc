# aliasing_not_alignment

Missed vectorization because of a **loop-carried memory dependence** (`a[i]` reads `a[i-1]`), not an alignment diagnosis. The real LLVM remark is an `UnsafeDep` analysis: "unsafe dependent memory operations in loop ... Backward loop carried data dependence." Modern Clang resolves pure pointer *aliasing* with a runtime check and vectorizes anyway, so the reproducible "memory-reason miss that is not alignment" on a current toolchain is this backward dependence. Expected label: `alignment_unlikely_from_evidence`.

## Expected alignment label

`alignment_unlikely_from_evidence`

## Compile

```bash
EX=aliasing_not_alignment
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
python -m explncc alignment-pack "$OUT/main.opt.yaml" \
  --include-source --source-root "$ROOT" \
  --format markdown
```

## Fixture

```bash
python -m explncc alignment fixtures/main.opt.yaml --json
```
