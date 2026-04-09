# Notes for Chapter 10 (progressive tool use)

Suggested pacing when the chapter introduces optimization remarks:

1. **Emit remarks** — Show `clang++` with `-fsave-optimization-record` and `-foptimization-record-file=`. Point readers at `make examples` so everyone reproduces the same `.opt.yaml` layout under `build/examples/`.
2. **Read structure** — Open `.opt.yaml` in an editor: YAML stream, `!Missed` / `!Passed` / `!Analysis` tags, `Args` variability. Motivate **normalization** (`explncc export`) for anything downstream.
3. **Summarize** — `explncc summary` and `explncc stats` to collapse thousands of lines into pass/function/kind counts.
4. **Compare builds** — `explncc diff` before/after pairs (`inline_too_costly` before vs after, or two `build/` trees). Tie to CI with `explncc check`.
5. **Interpret** — `explncc explain --backend rule` for stable pedagogy; optional `ollama` / `openai` for richer prose once the deterministic story is clear.

This order keeps the **deterministic core** authoritative; AI appears as an optional layer aligned with the book’s “AI-guided” framing without hiding the compiler’s own vocabulary.
