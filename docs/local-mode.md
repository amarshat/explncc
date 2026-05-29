# Local Mode

Local mode is explncc's offline-first intelligence path. It turns raw compiler
optimization remarks into ranked, explained, actionable findings **without any
network access, API keys, or model server**.

## Pipeline

```
.opt.yaml
  → parse            (toolchain adapter)
  → normalize        (OptimizationRecord)
  → classify         (rule-based local classifier)
  → rank             (deterministic weighted ranker)
  → explain          (template explanations from the label taxonomy)
  → report           (deterministic local report)
```

Only optional model backends are nondeterministic. Everything in local mode is
reproducible, testable, cacheable, and CI-safe.

## Modules

| Module | Responsibility |
|--------|----------------|
| `explncc/local/taxonomy.py` | The local label taxonomy (titles, severities, actions, templates). |
| `explncc/local/classifier.py` | Rule-based classifier → `ClassificationResult`. |
| `explncc/local/features.py` | Explainable feature extraction (`FeatureExtraction`). |
| `explncc/local/ranker.py` | `LocalRankerV1` deterministic weighted scorer → `RankedFinding`. |
| `explncc/local/ml_ranker.py` | Extension point for a future trained ranker (`LocalModelRanker`). |
| `explncc/local/explain.py` | Template-based explanations. |
| `explncc/local/report.py` | Deterministic local report (markdown / json). |
| `explncc/local/training_export.py` | Feature-row export for future model training. |

## Commands

### classify

```bash
explncc classify build/app.opt.yaml --local --format table
```

Options: `--format table|json|jsonl|markdown`, `--label-filter LABEL`,
`--min-confidence low|medium|high`, `--limit N`, `--focus alignment`,
`-o/--output`.

Output columns: function, location, pass, kind, label, confidence, reason,
recommended action.

### rank

```bash
explncc rank build/app.opt.yaml --local --top 20 --format markdown -o ranked.md
```

Options: `--format`, `--top N`, `--min-score FLOAT`, `--include-passed`,
`--ranker heuristic|model`, `--model-path PATH`, `--focus`, `-o/--output`.

Markdown emits `# Ranked Compiler Optimization Findings` with rank, score,
severity, label, compiler evidence, score reasons, and recommended actions.

### explain --local

```bash
explncc explain build/app.opt.yaml --local
```

Renders evidence-first explanations:

```
Compiler evidence:
- pass: loop-vectorize
- kind: Missed
- message: cannot prove memory independence

Local diagnosis:
- label: vectorize_aliasing
- confidence: high

Explanation:
The compiler attempted loop vectorization but could not prove memory
independence...

Recommended next steps:
1. Inspect whether input/output buffers can overlap.
2. Consider restrict/noalias only if semantically valid.
3. Review call sites for overlapping ranges.
```

### report --local

```bash
explncc report build/app.opt.yaml --local --format markdown -o report.md
```

Sections: Summary, Policy (if thresholds active), Top ranked findings, Local
diagnosis summary by label, Recommended actions, raw evidence references. No AI
section unless a model backend is explicitly requested.

## Conservatism

The classifier never overclaims:

- Weak evidence → `insufficient_evidence` or a `generic_*` label.
- Alignment labels require `--focus alignment`.
- Target-specific labels (wasm/neon/avx) require real target evidence.

See [classifier-labels.md](classifier-labels.md) for every label, and
[local-ranker.md](local-ranker.md) for scoring details.
