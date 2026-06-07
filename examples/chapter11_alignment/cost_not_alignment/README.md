# cost_not_alignment

Missed vectorization due to **cost / profitability**, not alignment. The real LLVM remark is an slp-vectorizer `NotBeneficial`: "List vectorization was possible but not beneficial with cost C >= Treshold T" (LLVM really does misspell the threshold key as `Treshold`). Expected label: `alignment_unlikely_from_evidence`.

## Expected alignment label

`alignment_unlikely_from_evidence`

## Compile

```bash
EX=cost_not_alignment
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
python -m explncc alignment-pack "$OUT/main.opt.yaml" --format json
```

## Fixture

```bash
python -m explncc alignment fixtures/main.opt.yaml --json
```
