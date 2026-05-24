# explncc

**Explain Compiler** — parse Clang/LLVM `.opt.yaml` optimization remark streams, normalize them into a stable schema, and drive **summary**, **stats**, **diff**, **export**, **check**, **explain**, **evidence packs** with optional **source / IR / assembly context**, **Chapter 11 alignment pipelines** (labels, packs, datasets, eval), and **Chapter 12 CI feedback** (stable JSON reports, semantic `report-diff`, policy gates, PR comments), plus **digest** and **doctor** for cache keys and masked config (Chapter 13 themes).

Companion tooling for *Decode the Compiler: AI-Guided Explanations of C/C++ Optimization Logs for Real-World Performance*.

## Why optimization logs matter

The compiler already decided what to optimize, what to skip, and often *why*. Those decisions are recorded as YAML streams with tags such as `!Missed`, `!Passed`, and `!Analysis`. Treating that output as data — rather than scrolling thousands of lines by hand — is what makes performance work reproducible and teachable.

## Why `.opt.yaml`

Clang can emit a machine-oriented record of optimization events tied to source locations. explncc:

- parses YAML **document streams** (not a single mapping),
- preserves remark **kind** from YAML tags,
- normalizes inconsistent `Args` into `message`, `cost`, `threshold`, and related fields **without inventing data**,
- supports **directory** inputs (all `*.opt.yaml` recursively).

## Lossless Semantic Tree (LST)

Chapter 10 introduces the **Lossless Semantic Tree (LST)** — a way to preserve and expose the compiler’s optimization reasoning without flattening it into prose or asking a model to guess from source alone.

| Word | Meaning in explncc |
|------|-------------------|
| **Lossless** | No invented facts. Raw `.opt.yaml` stays authoritative; normalization keeps `args_raw`; evidence packs list gaps in `missing_context`. |
| **Semantic** | The compiler already decided pass, kind, costs, vectorization, and DebugLoc — tooling surfaces *that* evidence, not LLM inference from source text. |
| **Tree** | Structured evidence around one remark: primary node, `related_records[]` links to sibling remarks in the same function/log, optional context leaves (source, IR, asm). |

```text
.opt.yaml remark (root evidence)
  └── OptimizationRecord (normalized node)
        └── EvidencePack (minimal semantic slice)
              ├── primary remark fields
              ├── related_records[]     ← linked remarks, same function/log
              └── optional context leaves
                    ├── source_snippet   (--include-source)
                    ├── ir_snippet       (--include-ir)
                    └── assembly_snippet (--include-asm)
```

**Chapter extensions:**

- **Chapter 11** — alignment labels and `alignment-pack` add classification nodes on the same tree (conservative teachers, eval rubrics).
- **Chapter 12** — `report` / `report-diff` treat one `.opt.yaml` as a snapshot and sequences across commits as **compiler-semantic history** (decision drift, not source diff).

**Prompt pipeline (Chapter 10 thesis):**

```text
.opt.yaml → normalized record → evidence pack → prompt template → optional explain
```

Model backends consume **normalized records or packs**, never raw YAML streams. Context attachment (`--include-source`, `--include-ir`, `--include-asm`) adds leaves when you have external artifacts; absent layers stay explicit.

| LST layer | explncc command |
|-----------|-----------------|
| Compiler record | `summary`, `stats`, `export`, `check`, `report` |
| Normalized record | all commands |
| Evidence pack | `explncc evidence` |
| Context leaves | `--include-source`, `--include-ir`, `--include-asm` on `evidence`, `alignment-pack`, `dataset` |
| Semantic CI history | `explncc report-diff` |

**Trust model (Chapters 10–12):**

1. Compiler YAML is authoritative.
2. CI organizes and preserves evidence.
3. Deterministic policy gates decide pass/fail.
4. Models optionally assist triage (clearly labeled sections in `report`).

See [docs/chapter-10-notes.md](docs/chapter-10-notes.md) for the teaching order and evidence-pack workflow.

## Install

```bash
python3.12 -m venv .venv
source .venv/bin/activate
make install-dev
```

## Quick start

```bash
make examples
python -m explncc summary build/examples/ --limit 20
python -m explncc stats build/examples/vectorize_aliasing_fail/ --json
python -m explncc diff \
  build/examples/inline_too_costly/before/before.opt.yaml \
  build/examples/inline_too_costly/after/after.opt.yaml
python -m explncc explain build/examples/inline_miss_no_definition/main.opt.yaml --backend rule
python -m explncc export build/examples/ --format jsonl -o /tmp/out.jsonl
python -m explncc check build/examples/ --max-missed-inline 200
```

### Chapter 10 (evidence packs + context extraction)

Build **deterministic evidence packs** from normalized remarks — the bridge between raw `.opt.yaml` and downstream training or explanation.

```bash
# One pack per remark (JSONL for pipelines)
python -m explncc evidence build/examples/inline_miss_no_definition/main.opt.yaml \
  --format jsonl -o /tmp/packs.jsonl

# Attach source window around DebugLoc (requires paths that resolve from --source-root)
python -m explncc evidence build/examples/vectorize_success/main.opt.yaml \
  --include-source --source-root examples/vectorize_success \
  --context-before 5 --context-after 8 \
  --format markdown -o /tmp/pack.md

# Join external IR / assembly (Clang does not embed these in .opt.yaml)
python -m explncc evidence tests/fixtures/simd_vectorized.opt.yaml \
  --include-ir --ir-file tests/fixtures/t.ll --ir-lines 50 \
  --include-asm --asm-file tests/fixtures/t.s --asm-lines 60 \
  --format json
```

Context flags are shared with `alignment-pack` and `dataset --focus alignment` (`--include-source`, `--include-ir`, `--include-asm`). See `src/explncc/context_snippets.py` for snippet bounds and assembly mnemonic hints (`movaps`, `vmovups`, …) — conservative signals, not diagnoses.

### Chapter 11 (SIMD / alignment + LLM datasets)

These commands are **deterministic**: they do not train or call a model unless you plug the output into your own tooling.

```bash
# Heuristic slice: vectorization-related remarks (pass names, keywords, vector width field)
python -m explncc alignment build/examples/vectorize_success/ --limit 20
python -m explncc alignment build/examples/ --json | head -c 600

# Alignment evidence packs: compiler facts + labels + optional LST context leaves
python -m explncc alignment-pack examples/chapter11_alignment/ \
  --format jsonl -o /tmp/alignment-packs.jsonl

python -m explncc alignment-pack examples/chapter11_alignment/aligned_intrinsic/fixtures/main.opt.yaml \
  --include-source --source-root examples/chapter11_alignment/aligned_intrinsic \
  --format markdown

# JSONL for fine-tuning / instruction tuning (OpenAI-style chat messages + optional metadata)
python -m explncc dataset build/examples/vectorize_aliasing_fail/ \
  -o /tmp/ch11_train.jsonl \
  --focus alignment \
  --template guided \
  --format explncc-record

# Prompt A/B fixtures + evaluator
python -m explncc bench-prompts examples/chapter11_alignment/ \
  --focus alignment --templates minimal,guided,rubric,adversarial,missing-context \
  -o /tmp/ch11_bench.jsonl

python -m explncc eval-alignment tests/fixtures/alignment_predictions.jsonl --format markdown

# Full fixture pipeline (no Clang required)
make chapter11
```

See [docs/chapter-11-alignment.md](docs/chapter-11-alignment.md) for the full pipeline guide and [docs/chapter-11-notes.md](docs/chapter-11-notes.md) for a short companion.

### Chapter 12 (CI feedback loop: reports, semantic diff, gates)

`explncc report` turns normalized remarks into **CI artifacts** (Markdown, JSON, GitHub, HTML). **`report-diff`** compares two `.opt.yaml` trees for **compiler-semantic drift** (what the optimizer decided changed), complementing source diffs. Policy gates are **deterministic only** — models never fail the build.

```bash
# GitHub Actions job summary (default: --no-explain, no network)
python -m explncc report build/app.opt.yaml --format markdown --title "Build remarks" \
  --git-sha "$GITHUB_SHA" --branch "$GITHUB_REF_NAME" --ci-provider github \
  >> "$GITHUB_STEP_SUMMARY"

# Stable JSON for dashboards (schema_version, summary, policy, metadata)
python -m explncc report build/app.opt.yaml --format json \
  --git-sha "$GITHUB_SHA" --ci-provider github \
  -o report.json --write-manifest manifest.json

# Collapsible PR comment body (post with gh pr comment --body-file)
python -m explncc report build/app.opt.yaml --format github --top-missed 10 -o pr-comment.md

# Deterministic gate (same thresholds as check; writes artifact even on failure)
python -m explncc report build/app.opt.yaml -o gate.md \
  --fail-on-check --max-missed-inline 80 --max-missed-vectorize 20

# Semantic diff: baseline vs PR build (regression / improvement classification)
python -m explncc report-diff build/baseline/app.opt.yaml build/pr/app.opt.yaml \
  --before-label main --after-label pr --format github --top-changes 15 \
  -o pr-diff-comment.md

# Optional triage only when policy fails (rule backend, no raw YAML to models)
python -m explncc report build/app.opt.yaml --format markdown \
  --fail-on-check --max-missed-inline 80 \
  --explain-backend rule --explain-only-on-failure -o gate.md

# Stable digests over collected .opt.yaml (CI cache keys) and masked backend env
python -m explncc digest build/
python -m explncc doctor
```

Copy-ready workflows: [examples/ci/](examples/ci/) (`explncc-report.yml`, `explncc-gated.yml`, `explncc-diff-pr.yml`). Full guide: [docs/chapter-12-ci.md](docs/chapter-12-ci.md). Short checklist: [docs/chapter-12-notes.md](docs/chapter-12-notes.md).

### Chapter 14 (diagrams + merged explanations)

`explncc viz` emits **Mermaid** diagrams, **HTML** with Mermaid.js, or **JSON** for your own graph UI — all from the same normalized remarks as the rest of the tool (not from LLVM IR bitcode).

```bash
python -m explncc viz build/examples/ --style pass-summary --format mermaid --top 12 -o remarks.mmd
python -m explncc viz build/app.opt.yaml --style pass-remark --format json -o viz.json
python -m explncc viz build/app.opt.yaml --style missed-top --format html --explain-backend rule -o viz.html
```

Author notes: [docs/chapter-14-notes.md](docs/chapter-14-notes.md). Demo: `make chapter14-demo`.

## Example output (summary)

Rich tables list `kind`, `pass`, `remark`, `function`, location, and a truncated `message`. Use `--json` or `--jsonl` for stable downstream tooling.

## Architecture

| Module | Role |
|--------|------|
| `explncc/parser.py` | YAML stream loader with `!Missed` / `!Passed` / `!Analysis` |
| `explncc/normalizer.py` | Raw document → `OptimizationRecord` |
| `explncc/models.py` | Pydantic schema |
| `explncc/summary.py` / `stats.py` | Filtering and aggregates |
| `explncc/diffing.py` | Build-vs-build missed deltas and counters |
| `explncc/report_diff.py` | Semantic optimization diff for CI (`report-diff`) |
| `explncc/exporters.py` | `json`, `jsonl`, `csv` |
| `explncc/checks.py` | Deterministic CI policy thresholds |
| `explncc/explain/` | Rule text + optional HTTP backends |
| `explncc/context_snippets.py` | Source / IR / assembly snippet extraction + asm signals |
| `explncc/evidence.py` | Chapter 10 evidence packs from normalized remarks |
| `explncc/alignment.py` | Heuristic SIMD / alignment-related remark slice + labels |
| `explncc/alignment_pack.py` | Chapter 11 alignment evidence packs |
| `explncc/prompt_templates.py` | Named Chapter 11 user prompts (`minimal`, `guided`, `rubric`) |
| `explncc/dataset_llm.py` | JSONL builders for training / bench rows |
| `explncc/ci_report.py` | Markdown / JSON / HTML / GitHub CI reports |
| `explncc/ci_manifest.py` | CI artifact manifest (`--write-manifest`, `ci-manifest`) |
| `explncc/report_types.py` | Stable JSON report schema + metadata types |
| `explncc/digest.py` | Per-file and aggregate SHA-256 over `.opt.yaml` inputs |
| `explncc/config.py` | Backend env + `doctor` payload |
| `explncc/viz.py` | Mermaid / HTML / JSON visualization bundles (`viz` command) |
| `explncc/cli.py` | Typer commands |

Subpackages stay small so a book chapter can point to one file at a time.

## Supported inputs

- Clang/LLVM `-fsave-optimization-record` / `-foptimization-record-file=…` output (`.opt.yaml`)
- One file or a directory tree; only `*.opt.yaml` files are read

## Limitations

- Heuristics depend on Clang’s YAML shape; newer LLVM versions may add fields (handled conservatively).
- **`alignment` slice** is keyword/pass-based, not semantic analysis; validate on your corpus before publishing benchmark numbers.
- **Diff** compares fingerprints of normalized rows; identical logical events with different wording may look distinct.
- **Context attachment** needs correct `--source-root` and external `.ll`/`.s` files; wrong paths yield empty snippets, not invented code.
- **Evidence / alignment packs** list `missing_context` explicitly; teachers and evaluators are conservative heuristics, not oracle labels.
- **AI backends** augment text only; they consume normalized records or packs, not raw `.opt.yaml`, and never drive CI pass/fail.
- **`dataset` / `bench-prompts`** emit structure for training; they do not guarantee your fine-tuning provider’s latest JSONL schema — verify against current API docs.
- **`report` with explanation enabled** can call remote model APIs; prefer `--no-explain` on high-frequency CI unless you control keys, quotas, and data-retention policy.

## Roadmap

- Deeper remark-specific extractors (more structured fields from `Args`)
- Optional SARIF or LSP-adjacent bridges
- Tighter CI recipes (`explncc check` presets)

## For readers of *Decode the Compiler*

Use the bundled `examples/` to emit real `.opt.yaml` on your machine, then run explncc to connect source patterns to compiler vocabulary.

| Chapter | Doc |
|---------|-----|
| 10 — LST, evidence packs, context | [chapter-10-notes.md](docs/chapter-10-notes.md) |
| 11 — alignment pipeline, context, datasets | [chapter-11-alignment.md](docs/chapter-11-alignment.md), [chapter-11-notes.md](docs/chapter-11-notes.md) |
| 12 — CI reports, semantic diff, gates | [chapter-12-ci.md](docs/chapter-12-ci.md), [chapter-12-notes.md](docs/chapter-12-notes.md) |
| 13–14 — architecture, viz | [chapter-13-notes.md](docs/chapter-13-notes.md), [chapter-14-notes.md](docs/chapter-14-notes.md) |

## Why not just read `.opt.yaml` manually?

You can — and you should, once — to see the raw stream. explncc exists so you can **filter**, **count**, **diff across builds**, and **export** the same information reliably for notes, CI, and (optionally) model-assisted prose.

## Design principles

1. **Deterministic core first** — every command works without network access.
2. **No invented fields** — missing data stays absent; `args_raw` preserves the source.
3. **AI as augmentation** — rule text is always available; HTTP backends only enrich labeled sections.
4. **LST context leaves** — attach source/IR/asm when available; never fabricate missing layers.
5. **Semantic history** — one `.opt.yaml` is an LST snapshot; sequences across builds support `report-diff` drift analysis.

## Optional model backends

- **Ollama** (local): set `OLLAMA_HOST`, `OLLAMA_MODEL` (default `qwen2.5-coder:7b-instruct`).
- **OpenAI**: set `OPENAI_API_KEY`; optional `OPENAI_MODEL` (default `gpt-4o-mini`).

See [docs/model-backends.md](docs/model-backends.md).

## Building the book examples

```bash
brew install llvm   # macOS
make examples       # writes under build/examples/<name>/
```

Details: [docs/getting-started.md](docs/getting-started.md) and [docs/examples.md](docs/examples.md).

## Contributing

- `make check` — ruff, format check, mypy, pytest
- `make docs-check` — required doc files present
- Prefer focused changes with tests beside `tests/fixtures/*.opt.yaml`

## Development workflow

```bash
make install-dev
make check
make demo          # needs `make examples` first
make chapter11-demo PYTHON="$(pwd)/.venv/bin/python3"   # alignment + bench-prompts sample
make chapter12-demo PYTHON="$(pwd)/.venv/bin/python3"     # CI-style github report (fixture)
```

### Testing Chapter 11 features

```bash
make check
python -m explncc alignment tests/fixtures/simd_vectorized.opt.yaml --json
python -m explncc dataset tests/fixtures/simd_vectorized.opt.yaml -o /tmp/t.jsonl --focus all --format openai-messages --template minimal
python -m explncc bench-prompts tests/fixtures/simd_vectorized.opt.yaml --focus all --templates minimal
```

### Testing evidence packs and context

```bash
python -m explncc evidence tests/fixtures/simd_vectorized.opt.yaml --format json | head -c 800
python -m pytest -q tests/test_evidence.py tests/test_context_snippets.py
```

### Testing Chapter 12 (`report` / `report-diff`)

```bash
python -m explncc report tests/fixtures/inline_miss_no_definition.opt.yaml --format markdown
python -m explncc report tests/fixtures/inline_miss_no_definition.opt.yaml --format github | head -n 20
python -m explncc report-diff tests/fixtures/inline_miss_no_definition.opt.yaml \
  tests/fixtures/inline_miss_no_definition.opt.yaml --format markdown
python -m pytest -q tests/test_ci_report.py tests/test_report_cli.py tests/test_chapter12_ci.py
```

## License

MIT
