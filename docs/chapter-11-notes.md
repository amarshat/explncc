# Notes for Chapter 11 (alignment / SIMD + LLM training)

Chapter outline: *Training an LLM to diagnose memory misalignment (SSE/AVX)* — dataset design, fine-tuning vs instruction tuning, and evaluation.

## How explncc supports this chapter (objectively)

explncc does **not** train models. It gives you **deterministic** building blocks:

1. **A reproducible slice of compiler remarks** that often co-occur with SIMD and alignment discussions (`explncc alignment`). The signals are **heuristics** (pass names, substrings, `vectorization_factor`); they are useful for filtering, not ground truth.
2. **Prompt–completion JSONL** derived from normalized remarks plus optional rule-based “teacher” text (`explncc dataset`). You can swap the teacher for human labels, larger models, or IR-augmented prompts in your own pipeline.
3. **Prompt A/B fixtures** as JSONL (`explncc bench-prompts`) so you can run the same records through multiple prompt shapes and compare model outputs offline.

## Mapping to main headings

| Chapter heading | explncc hooks |
|-----------------|---------------|
| Why alignment matters in vectorization | Teach from raw `.opt.yaml`, then `alignment` + `explain --backend rule` on vector passes. |
| Case study setup (SSE/AVX edge failures) | `make examples`; compare `vectorize_aliasing_fail` vs `vectorize_success`; `diff` optional. |
| Constructing a prompt–completion dataset | `dataset --focus alignment --template guided --format explncc-record`; add IR in a separate column/tool. |
| Fine-tuning vs instruction tuning | Same JSONL works for both: use `openai-messages` for chat fine-tuning APIs; use `explncc-record` when you need metadata for papers. |
| Prompt quality benchmarks | `bench-prompts --templates minimal,guided,rubric` then score responses in your evaluator. |

## IR in the loop

Clang IR is **not** embedded in `.opt.yaml`. For “remark + IR + response” rows, keep IR generation outside explncc (e.g. `clang -emit-llvm -S`) and join on `(file, line)` or your own build IDs. explncc `metadata` fields are there to anchor that join.

## Limitations (state these in the book)

- Heuristic `alignment` slice can **miss** subtle remarks or **include** irrelevant ones.
- Rule-based teachers are **short** and generic; they are baselines, not oracle labels.
- Model APIs and fine-tuning formats change; validate JSONL against your provider’s current spec.
