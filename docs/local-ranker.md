# Local Ranker

`LocalRankerV1` (`explncc/local/ranker.py`) answers one question:

> Which compiler remarks are most likely worth a developer's attention?

It is deterministic, explainable, and has no ML dependency. Scores express
**developer relevance**, not absolute truth; compiler evidence remains
authoritative.

## Feature extraction

`explncc/local/features.py` turns each `OptimizationRecord` into a simple,
explainable feature vector plus human-readable reasons. Features are binary or
small integers and fall into groups:

- **Basic:** `kind_is_missed`, `kind_is_passed`, `kind_is_analysis`,
  `has_source_location`, `has_function`, `has_debug_location`, `has_cost`,
  `has_vectorization_factor`, `has_interleave_count`, `has_target`,
  `has_source_snippet`, `has_ir_snippet`, `has_assembly_snippet`.
- **Pass family:** `pass_loop_vectorize`, `pass_slp_vectorize`, `pass_inline`,
  `pass_unroll`, `pass_licm`, `pass_instcombine`, `pass_gvn`.
- **Message signals:** `msg_alias`, `msg_memory_independence`, `msg_cost`,
  `msg_threshold`, `msg_no_definition`, `msg_call`, `msg_trip_count`,
  `msg_reduction`, `msg_alignment`, `msg_vectorized`, `msg_runtime_check`.
- **Location/context:** `function_name_present`, `file_present`, `line_present`.
- **Optional diff features** (via `DiffContext`): `appeared_in_current_build`,
  `disappeared_from_baseline`, `changed_from_passed_to_missed`,
  `changed_from_missed_to_passed`, `cost_increased`,
  `vectorization_factor_decreased`.

`FEATURE_NAMES` gives a stable ordering for vectors and exports. Each set comes
with reasons, e.g. `"message mentions memory independence"`.

## Weighted scoring

The ranker combines the rule classification with the feature vector using a
transparent weighted sum. Representative weights:

| Signal | Weight |
|--------|--------|
| Missed remark | +30 |
| loop-vectorize miss | +25 |
| inline miss | +20 |
| cost-model rejection | +15 |
| aliasing / memory independence | +20 |
| has source location | +5 |
| no source location | −5 |
| has cost details | +8 |
| appeared in diff | +20 |
| changed Passed → Missed | +40 |
| profile hotness (when available) | 0 … +30 |
| repeated same-function cluster | +5 … +20 |
| generic analysis remark | −10 |
| passed remark (unless `--include-passed`) | −20 |

## Score reasons

Every weight applied records a reason, so each finding is fully auditable:

```
+30 because remark is Missed
+25 because pass is loop-vectorize and the remark is Missed
+20 because message mentions memory independence / aliasing
+5 because a source location is available
```

## Severity mapping

Raw score maps to severity:

| Score | Severity |
|-------|----------|
| ≥ 85 | critical |
| 70 – 84 | high |
| 45 – 69 | medium |
| < 45 | low |

`normalized_score` is the raw score clamped to `[0, 1]` (score / 100), useful as
a feature/target for future models.

## Tuning weights

Weights live as named contributions in `_score_one` in `ranker.py`. To tune:

1. Adjust the constant passed to `add(...)` for the relevant signal.
2. Re-run `explncc rank <fixtures> --format jsonl` and inspect `score_reasons`.
3. Confirm `tests/test_local_ranker.py` still encodes the intended ordering;
   update expected scores if you intentionally changed a weight.

Keep changes explainable: prefer a small number of clearly-named weights over
opaque tuning.

## Exporting training data

```bash
explncc export-training build/app.opt.yaml \
  --include-labels-from rules --format jsonl -o training.jsonl
```

Each row contains the feature vector, the rule label/confidence, a normalized
score, a compact text field, and metadata. See `export-training --format csv`
for a flat, one-column-per-feature layout.

## Future path: sklearn / BERT / ONNX

`LocalRankerV2` is an extension point only (`explncc/local/ml_ranker.py`). A
future trained model can implement `LocalModelRanker.load(path)` /
`.rank(records)` and be selected with `--ranker model --model-path PATH`,
behind an optional `explncc[ml]` extra. No model is trained or bundled today;
requesting `--ranker model` fails clearly until one exists.

Suggested progression:

1. Collect labeled rows with `export-training` across many builds.
2. Train a small sklearn classifier/ranker on the feature vectors.
3. Optionally move to a text model (BERT) over the `text` field, or export to
   ONNX for portable inference.
4. Keep the heuristic ranker as the deterministic, dependency-free default.
