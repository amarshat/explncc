# Toolchain notes

## Supported today

**Clang/LLVM** optimization record YAML:

```bash
clang++ -O3 -fsave-optimization-record \
  -foptimization-record-file=build/app.opt.yaml \
  app.cpp -o app
```

Adapter: `explncc.toolchains.clang.ClangOptYamlAdapter` (default `--toolchain clang`).

## Not supported yet (documented boundary)

| Toolchain | Typical artifacts | Notes |
|-----------|-------------------|-------|
| GCC | `-fopt-info`, `-fdump-tree-*` | Text/tree dumps — needs separate parser |
| MSVC | `/FA`, Diagnostic Tools | Different artifact shape |

The `ToolchainAdapter` interface in `toolchains/base.py` exists so future adapters can plug in without rewriting the CLI orchestration layer.

## Do not claim

Until parsers exist, do not document GCC/MSVC as supported inputs. Sidebar in the book can reference external tools (opt-diff, custom tree parsers) for non-Clang stacks.
