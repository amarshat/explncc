# Toolchain notes

## Supported today

**Clang/LLVM** optimization record YAML:

```bash
clang++ -O3 -fsave-optimization-record \
  -foptimization-record-file=build/app.opt.yaml \
  app.cpp -o app
```

Adapter: `explncc.toolchains.clang.ClangOptYamlAdapter` (default `--toolchain clang`).

## Supported (experimental): HLS synthesis reports

**High-level synthesis** loop-pipelining reports, via `--toolchain hls`. The
same opacity problem as a CPU optimization remark, sharper: the hidden decision
is a loop's *initiation interval* (II) and whether it pipelined at all.

```bash
# Vitis HLS already emits a per-solution csynth.xml; point explncc at it.
python -m explncc summary solution1/syn/report/ --toolchain hls
python -m explncc explain solution1/syn/report/csynth.xml --backend rule --toolchain hls
python -m explncc diff before/csynth.xml after/csynth.xml --toolchain hls
```

Adapter: `explncc.toolchains.hls.HlsReportAdapter`. It parses reports the
synthesis tool already produced; it does **not** run Vitis/Vivado. Each loop
becomes one `OptimizationRecord`:

| Outcome | `kind` | `remark_name` | II mapping |
|---------|--------|---------------|------------|
| pipelined at/below target | `passed` | `Pipelined` | `cost`=achieved II, `threshold`=target II |
| target II not met | `missed` | `IINotAchieved` | achieved II `>` target II |
| loop left un-pipelined | `missed` | `LoopNotPipelined` | no II |

Achieved/target II also populate the display fields `initiation_interval`,
`target_ii`, `loop_latency`, `trip_count`. Because achieved/target II map onto
the already-hashed `cost`/`threshold`, `diff` and `report-diff` flag II drift
(e.g. an II=1 loop regressing to II=3) for free. Today the Vitis `csynth.xml`
shape is parsed; the `.rpt` text and Intel/Vivado flavors are future work.

## Not supported yet (documented boundary)

| Toolchain | Typical artifacts | Notes |
|-----------|-------------------|-------|
| GCC | `-fopt-info`, `-fdump-tree-*` | Text/tree dumps — needs separate parser |
| MSVC | `/FA`, Diagnostic Tools | Different artifact shape |

The `ToolchainAdapter` interface in `toolchains/base.py` exists so future adapters can plug in without rewriting the CLI orchestration layer.

## Do not claim

Until parsers exist, do not document GCC/MSVC as supported inputs. Sidebar in the book can reference external tools (opt-diff, custom tree parsers) for non-Clang stacks.
