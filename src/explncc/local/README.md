# `explncc.local` — offline intelligence (no model server)

This package is explncc’s **local equivalent** of a small ML stack: it turns normalized
compiler remarks into labels, scores, and explanations **without** training a neural
network, **without** calling OpenAI/Claude/Ollama, and **without** requiring API keys.

Think of it as three layers that usually live inside a product model:

1. **Classifier** — “what kind of issue is this?”
2. **Ranker** — “how much should a developer care?”
3. **Explainer** — “what should they do next?”

Here, layers 1–3 are **rules + weights + templates**, not BERT or an SLM.

## Deterministic vs stochastic

| Kind | In this package | Typical “model” analogue | Network? |
|------|-----------------|---------------------------|----------|
| **Deterministic** | Parse/normalize (outside this pkg), taxonomy, rule classifier, feature extraction, `LocalRankerV1`, template explain/report, `export-training` rows | Rule engine + linear scorer + mail-merge templates | No |
| **Stochastic / learned** | *Not implemented yet* — hook only: `LocalModelRanker` (`ml_ranker.py`) | sklearn ranker, BERT classifier, ONNX, or an SLM for prose | Only if you add a trained artifact later |
| **Stochastic / hosted** | *Not in this package* — `explncc explain --backend openai\|claude\|ollama` | SLM / LLM explanation backends | Yes (opt-in) |

**Deterministic** means: same `.opt.yaml` → same labels, scores, reasons, and text (modulo
explicit CLI flags like `--include-passed`). Safe for CI, caching, and diffs.

**Stochastic** means: sampling or learned weights can change output between runs or
versions. explncc keeps that **outside** the local path on purpose; only optional
hosted backends or a future on-disk model do that.

Compiler **evidence** (pass, kind, message from Clang) stays authoritative. Local
labels and scores mean **developer relevance**, not ground truth.

## Pipeline (what runs in `--local` mode)

```
.opt.yaml
  → parse / normalize     (toolchains — not in this package)
  → classify              classifier.py   — rule-based labels
  → extract features      features.py     — explainable feature vector
  → rank                  ranker.py       — LocalRankerV1 weighted score
  → explain               explain.py      — taxonomy templates
  → report                report.py       — structured markdown/json
```

CLI entry points: `explncc classify`, `rank`, `explain --local`, `report --local`,
`export-training`.

## Categories: what is what?

### Classifier (shipped: **rule-based**, not BERT)

- **Module:** `classifier.py` + label definitions in `taxonomy.py`
- **Input:** one `OptimizationRecord` (+ optional `EvidencePack`)
- **Output:** `ClassificationResult` — `label`, `confidence`, `evidence_reasons`,
  `recommended_actions`
- **Method:** substring/pass/kind rules; conservative fallbacks (`insufficient_evidence`,
  `generic_*`)
- **Analogue:** hand-written decision tree or regex taxonomy — **not** a fine-tuned BERT
  text classifier (that would consume the `text` field from `export-training` later)

### Ranker (shipped: **heuristic V1**, not sklearn yet)

- **Module:** `ranker.py` (`LocalRankerV1`)
- **Input:** batch of records; uses classifier + `features.py`
- **Output:** `RankedFinding` — `rank`, `score`, `severity`, `score_reasons`, etc.
- **Method:** fixed weights (+30 missed, +25 loop-vectorize miss, …) with a reason per term
- **Analogue:** linear model with known coefficients — **not** a trained sklearn/ONNX ranker
- **Future:** `ml_ranker.py` — `LocalModelRanker.load(path).rank(...)` for sklearn/BERT/ONNX;
  select with `explncc rank --ranker model --model-path …` (fails clearly until implemented)

### Feature extraction (shipped: **tabular, explainable**)

- **Module:** `features.py`
- **Output:** binary/small-int features + human `reasons` (e.g. `msg_memory_independence`)
- **Use:** scoring today; **training rows** tomorrow (`training_export.py` → jsonl/csv)

### Explainer (shipped: **templates**, not SLM)

- **Module:** `explain.py` + `explanation_template` per label in `taxonomy.py`
- **Method:** fill structured sections (compiler evidence → local diagnosis → explanation → steps)
- **Analogue:** deterministic mail merge — **not** an SLM rewriting the remark
- **Contrast:** `explncc explain --backend openai` is a separate, stochastic, hosted path

### Taxonomy (shipped: **schema + copy**)

- **Module:** `taxonomy.py`
- **20 labels** (e.g. `vectorize_aliasing`, `inline_no_definition`, `generic_analysis`)
- Each label: `title`, `severity_default`, `recommended_actions`, `matching_hints`, template text

### Training export (shipped: **dataset builder**, not training)

- **Module:** `training_export.py`
- **Purpose:** emit `{ features, rule_label, rule_confidence, score, text, metadata }` for
  future sklearn / BERT / ONNX training — **no trainer** in this repo yet

## Module map

| File | Role |
|------|------|
| `contracts.py` | Shared types: `ClassificationResult`, confidence/severity |
| `taxonomy.py` | Label catalog and templates |
| `classifier.py` | Rule-based classifier |
| `features.py` | Feature vector + reasons |
| `ranker.py` | `LocalRankerV1` weighted ranker |
| `ml_ranker.py` | Extension point for learned ranker (stub) |
| `explain.py` | Template explanations |
| `report.py` | Local report builder |
| `output.py` | Table/json/markdown renderers for classify/rank |
| `training_export.py` | JSONL/CSV export for future ML |

## Quick mental model

```
                    ┌─────────────────────────────────────┐
  COMPILER          │  explncc.local (deterministic)     │
  EVIDENCE          │  rules → features → weights → tpl  │
  (.opt.yaml)       └─────────────────────────────────────┘
                              │
         optional later       │  optional hosted (not local)
                              ▼
                    ┌─────────────────┐   ┌──────────────────┐
                    │ sklearn/BERT/   │   │ OpenAI / Claude  │
                    │ ONNX ranker     │   │ Ollama (SLM)     │
                    │ (ml_ranker)     │   │ (explain/backends)│
                    └─────────────────┘   └──────────────────┘
                     learned, on-disk        stochastic, network
```

## Docs

- [docs/offline-first.md](../../../docs/offline-first.md) — flags, defaults, CI
- [docs/local-mode.md](../../../docs/local-mode.md) — commands and pipeline
- [docs/local-ranker.md](../../../docs/local-ranker.md) — weights, severity, tuning
- [docs/classifier-labels.md](../../../docs/classifier-labels.md) — every label

## Tests

Fixtures: `tests/fixtures/local_ranker/*.opt.yaml`  
Coverage: `tests/test_local_*.py` (classifier, features, ranker, CLI, offline guards, fixtures)
