# The EMA demo: one loop, two compilers, same disease

`ema.cpp` holds two loops every trading system has. The mid-price loop has
independent lanes and vectorizes. The exponential moving average reads its own
previous output, so it never will: the recurrence is the algorithm.

The interesting part is that both compilers already told you. Clang wrote the
verdict into `.opt.yaml`; Vitis HLS wrote the same verdict, in hardware terms,
into `csynth.xml`. `explncc why` reads both.

## CPU

```bash
clang++ -O3 -std=c++17 -fsave-optimization-record -c ema.cpp
explncc why . --pass loop-vectorize --top 0
```

```text
ema.cpp:13  ema(float*, float const*, float, int)
  MISS  not vectorized: loop-carried dependence  [loop-vectorize, 2 records]
   12 | void ema(float* out, const float* px, float alpha, int n) {
   13 |     for (int i = 1; i < n; ++i)
      |                ^
  compiler: unsafe dependent memory operations in loop. Backward loop carried data
            dependence. Memory location is the same as accessed at ema.cpp:14:51
  suggest:  Use #pragma clang loop distribute(enable) to allow loop distribution to
            attempt to isolate the offending operations into a separate loop

ema.cpp:7  mid_price(float*, float const*, float const*, int)
  OK  vectorized (width 4, interleave 4)  [loop-vectorize]
```

(Output above is from Apple clang 17 on arm64; on x86-64/AVX2 the width is 8.)

## FPGA

`ema_csynth.xml` is a representative Vitis HLS synthesis report for the same
kernel with `PIPELINE II=1` requested on both loops (shaped exactly like the
per-loop section Vitis emits; regenerate with a real Vitis run if you have the
toolchain). Same command, same record shape:

```bash
explncc why ema_csynth.xml --toolchain hls
```

```text
loop 'EMA_LOOP'  ema_kernel
  MISS  II target missed (achieved 3 vs target 1)  [hls-pipeline]
  compiler: loop 'EMA_LOOP', initiation interval II=3, target II=1, latency=4 cycles,
            trip count=4096; Unable to achieve II=1; carried dependency on out[i-1]
            (value written 1 iteration earlier, read 3 cycles later) forces II=3

loop 'MID_LOOP'  ema_kernel
  OK  pipelined (II=1)
```

Same serial recurrence, two very different toolchains, one diagnosis. On the
CPU it costs you SIMD lanes; on the FPGA it costs you initiation interval. No
amount of pragma-waving fixes either, because the dependence is real; knowing
that before you spend an afternoon on it is the point.

## Optional: a local model annotates it

```bash
explncc why . --missed-only --explain --model qwen2.5-coder:3b
```

Each missed finding gets a short streamed note from an on-device model,
grounded in the compiler evidence above it, with a latency line on stderr.
Nothing leaves the machine.
