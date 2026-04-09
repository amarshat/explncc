# Example programs

Each directory under `examples/` is a minimal C++ program aimed at one optimization story. Sources are commented; binaries and `.opt.yaml` files are produced under `build/examples/<name>/` by the top-level `Makefile` or `scripts/build_all_examples.sh`.

| Directory | Intent |
|-----------|--------|
| `inline_miss_no_definition` | Callee not visible in this TU: inliner cannot legally inline across missing definition. |
| `inline_too_costly` | `before/` vs `after/`: heavy callee rejected for size/cost; simplified callee becomes eligible. |
| `vectorize_aliasing_fail` | Possible aliasing between pointers: loop-vectorize may skip SIMD. |
| `vectorize_success` | Independent accesses (e.g. `restrict`-style contract): vectorization can succeed at `-O3`. |
| `unroll_fixed_trip` | Small constant trip count: loop unrolling is predictable. |
| `unroll_unknown_trip` | Trip count from memory/unknown: full unroll less likely; remarks show uncertainty tradeoffs. |

Use `explncc summary` and `explncc explain` on the generated `.opt.yaml` to connect source patterns to compiler language.
