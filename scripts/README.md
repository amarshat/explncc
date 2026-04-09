# scripts

Shell entry points used by the top-level `Makefile` and by readers who prefer explicit commands over `make`.

| Script | Role |
|--------|------|
| `build_example.sh` | Build one example via Make (`vectorize_aliasing_fail`, `inline_too_costly`, …). |
| `build_all_examples.sh` | Runs `make build-all-opt`. |
| `run_summary.sh` | Runs `explncc summary` on `build/examples` (or first argument). |
| `run_stats.sh` | Runs `explncc stats` on `build/examples` (or first argument). |
| `run_explain.sh` | Thin wrapper around `explncc explain`. |

Make all scripts executable in the repo: `chmod +x scripts/*.sh` (also done by `git update-index --chmod=+x` when needed).
