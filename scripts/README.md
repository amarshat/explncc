# scripts

Shell entry points used by the top-level `Makefile` and by readers who prefer explicit commands over `make`.

| Script | Role |
|--------|------|
| `build_example.sh` | Build one example: emits binary and `.opt.yaml` under `build/examples/<name>/`. |
| `build_all_examples.sh` | Iterate all examples (invoked by `make examples`). |
| `run_summary.sh` | Run `explncc summary` over `build/examples` (used by `make summarize-all`). |
| `run_explain.sh` | Run `explncc explain` with a chosen backend (used by `make explain-all` / demos). |

Scripts are added in the same milestone as the example sources so they never point at missing files.
