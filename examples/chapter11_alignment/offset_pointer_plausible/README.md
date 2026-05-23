# offset_pointer_plausible

Loop uses `input + 1` — memory layout **may** matter for alignment, but a typical vectorization remark does not prove a misalignment issue. Expected label: `alignment_plausible_not_proven` unless IR/assembly provides stronger evidence.

## Expected alignment label

`alignment_plausible_not_proven`

## Compile

```bash
EX=offset_pointer_plausible
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
  --include-ir --ir-file "$OUT/main.ll" \
  --include-asm --asm-file "$OUT/main.s" \
  --format markdown
```

## Fixture

```bash
python -m explncc alignment fixtures/main.opt.yaml --json
```
