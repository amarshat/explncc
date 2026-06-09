# explncc

explncc (Explain Compiler) reads Clang/LLVM `.opt.yaml` optimization-remark streams, normalizes them into a stable schema, and runs deterministic analysis over them: summary, stats, diff, export, check, explain, evidence packs, alignment pipelines, CI reports and semantic diffs, policy gates, visualization, and digest/doctor for cache keys and masked configuration. Optional model backends turn a normalized remark into a short explanation; they are the only nondeterministic part of the tool.

It is the companion tooling for the book *Decode the Compiler: LLM-Guided Explanations of C/C++ Optimization Logs for Real-World Performance*.

## Sixty seconds to the first answer

Recompile with optimization records, then ask about the loop you care about:

```bash
clang++ -O3 -fsave-optimization-record -c hot.cpp
explncc why hot.cpp:11
```

```text
hot.cpp:11  scan(float*, float const*, int)
  MISS  not vectorized: loop-carried dependence  [loop-vectorize, 2 records]
   10 | void scan(float* a, const float* b, int n) {
   11 |     for (int i = 1; i < n; ++i) a[i] = a[i-1] + b[i];
      |                                      ^
  compiler: unsafe dependent memory operations in loop. Backward loop carried data
            dependence. Memory location is the same as accessed at hot.cpp:11:40
  suggest:  Use #pragma clang loop distribute(enable) to allow loop distribution to
            attempt to isolate the offending operations into a separate loop
```

Everything in that block is the compiler's own evidence: `why` fuses the
`!Missed` rollup with its sibling `!Analysis` cause, demangles the function,
quotes the source line with a caret at the reported column, and extracts the
compiler's suggestion verbatim. No model was involved. Add one when you want
prose: `explncc why hot.cpp:11 --explain` streams a two-sentence note from a
local model under each missed finding, grounded in the same evidence.

`explncc why` with no arguments triages the whole directory: misses first,
noise hidden, wins included so you know what already worked. Details:
[docs/why-and-fusion.md](docs/why-and-fusion.md).

## Why optimization logs matter

The compiler already decided what to optimize, what to skip, and often why. It records those decisions as YAML streams tagged `!Missed`, `!Passed`, and `!Analysis`. Reading that output as data, instead of scrolling thousands of lines by hand, is what makes performance work reproducible and reviewable.

## Why `.opt.yaml`

Clang emits a machine-oriented record of optimization events tied to source locations. explncc:

- parses YAML document streams (not a single mapping),
- preserves the remark kind from the YAML tag,
- normalizes inconsistent `Args` into `message`, `cost`, `threshold`, and related fields without inventing data,
- accepts directory inputs (all `*.opt.yaml` files, recursively).

## Lossless Semantic Tree (LST)

Chapter 10 introduces the Lossless Semantic Tree, a way to preserve the compiler's optimization reasoning without flattening it into prose or asking a model to guess from source alone.

| Term | Meaning in explncc |
|------|-------------------|
| Lossless | No invented facts. Raw `.opt.yaml` stays authoritative, normalization keeps `args_raw`, and evidence packs list gaps in `missing_context`. |
| Semantic | The compiler already decided pass, kind, costs, vectorization, and DebugLoc. The tooling surfaces that evidence rather than inferring from source text. |
| Tree | Structured evidence around one remark: a primary node, `related_records[]` linking sibling remarks in the same function or log, and optional context leaves (source, IR, assembly). |

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

Chapter extensions:

- Chapter 11 adds alignment labels and `alignment-pack`, which attach classification nodes to the same tree (conservative teachers, eval rubrics).
- Chapter 12 treats one `.opt.yaml` as a snapshot and a sequence across commits as compiler-semantic history, which `report` and `report-diff` read as decision drift rather than source diff.

The prompt pipeline (the Chapter 10 thesis):

```text
.opt.yaml → normalized record → evidence pack → prompt template → optional explain
```

Model backends consume normalized records or packs, never raw YAML streams. The context flags (`--include-source`, `--include-ir`, `--include-asm`) add leaves when you have the external artifacts; absent layers stay explicit instead of being filled in.

| LST layer | explncc command |
|-----------|-----------------|
| Compiler record | `summary`, `stats`, `export`, `check`, `report` |
| Normalized record | all commands |
| Evidence pack | `explncc evidence` |
| Context leaves | `--include-source`, `--include-ir`, `--include-asm` on `evidence`, `alignment-pack`, `dataset` |
| Semantic CI history | `explncc report-diff` |
| Cross-toolchain (experimental) | `--toolchain hls` on `summary`, `stats`, `diff`, `explain`, `evidence`, `report`, `check`, `report-diff`, `viz` |

The same LST shape extends past the CPU. `--toolchain hls` reads the synthesis reports an HLS tool already emits (Vitis `csynth.xml` today) and turns each loop's initiation-interval decision into the same `OptimizationRecord` the rest of the pipeline consumes. Same opacity problem, sharper. See [docs/toolchain-notes.md](docs/toolchain-notes.md).

The trust model (Chapters 10 to 12):

1. Compiler YAML is authoritative.
2. CI organizes and preserves the evidence.
3. Deterministic policy gates decide pass or fail.
4. Models optionally assist triage, in clearly labeled sections of `report`.

See [docs/chapter-10-notes.md](docs/chapter-10-notes.md) for the teaching order and the evidence-pack workflow.

## Install

```bash
python3.12 -m venv .venv
source .venv/bin/activate
make install-dev
```

## Quick start

```bash
make examples
python -m explncc why build/examples/                # fused findings, misses first
python -m explncc why build/examples/ --missed-only --explain   # + local model notes
python -m explncc summary build/examples/ --limit 20
python -m explncc stats build/examples/vectorize_aliasing_fail/ --json
python -m explncc diff \
  build/examples/inline_too_costly/before/before.opt.yaml \
  build/examples/inline_too_costly/after/after.opt.yaml
python -m explncc explain build/examples/inline_miss_no_definition/main.opt.yaml --backend rule
python -m explncc export build/examples/ --format jsonl -o /tmp/out.jsonl
python -m explncc check build/examples/ --max-missed-inline 200
```

### Evidence packs and context extraction

Evidence packs are deterministic slices built from normalized remarks. They are the bridge between a raw `.opt.yaml` and downstream training or explanation.

```bash
# One pack per remark (JSONL for pipelines)
python -m explncc evidence build/examples/inline_miss_no_definition/main.opt.yaml \
  --format jsonl -o /tmp/packs.jsonl

# Attach a source window around DebugLoc (paths must resolve from --source-root)
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

The context flags are shared with `alignment-pack` and `dataset --focus alignment`. See `src/explncc/context_snippets.py` for the snippet bounds and the assembly mnemonic hints (`movaps`, `vmovups`, and so on), which are conservative signals, not diagnoses.

### SIMD / alignment analysis and LLM datasets

These commands are deterministic. They do not train or call a model unless you feed the output into your own tooling.

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

See [docs/chapter-11-alignment.md](docs/chapter-11-alignment.md) for the full pipeline guide and [docs/chapter-11-notes.md](docs/chapter-11-notes.md) for the short companion.

### CI feedback loop: reports, semantic diff, gates

`explncc report` turns normalized remarks into CI artifacts (Markdown, JSON, GitHub, HTML). `report-diff` compares two `.opt.yaml` trees for compiler-semantic drift, which is what the optimizer decided differently, and complements a source diff. Policy gates are deterministic; a model never fails the build.

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

# Deterministic gate (same thresholds as check; writes the artifact even on failure)
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

Copy-ready workflows live in [examples/ci/](examples/ci/) (`explncc-report.yml`, `explncc-gated.yml`, `explncc-diff-pr.yml`). Full guide: [docs/chapter-12-ci.md](docs/chapter-12-ci.md). Short checklist: [docs/chapter-12-notes.md](docs/chapter-12-notes.md).

### Compiler-semantic infrastructure

Only the explanation backends are nondeterministic. Parse, normalize, identity hashes, evidence packs, reports, and digests are reproducible and CI-safe.

```bash
# Pipeline visibility (teaching / debugging)
python -m explncc trace build/examples/vectorize_success/ \
  --format markdown --include-sample-record --include-evidence -o build/chapter13/trace.md

# Cache keys over compiler evidence (not binaries)
python -m explncc digest build/examples/ --include-evidence

# Masked backend config (safe for CI logs)
python -m explncc doctor --format markdown

# Standalone HTML report with embedded CSS
python -m explncc report build/app.opt.yaml --format html --embed-json -o report.html

# Structured explanation result (rule / auto with fallback)
python -m explncc explain build/app.opt.yaml --backend auto
```

Full guide: [docs/architecture.md](docs/architecture.md). Examples: [examples/chapter13_architecture/](examples/chapter13_architecture/). Demo: `make chapter13-demo`.

### Diagrams and merged explanations

`explncc viz` emits Mermaid diagrams, HTML with Mermaid.js, or JSON for your own graph UI, all from the same normalized remarks as the rest of the tool (not from LLVM IR bitcode). The diagrams are diagnostic views, not the LLVM pass pipeline, and the output says so.

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
| `explncc/parser.py` | YAML stream loader, preserving `!Missed` / `!Passed` / `!Analysis` |
| `explncc/normalizer.py` | Raw document to `OptimizationRecord` |
| `explncc/models.py` | Pydantic schema and stable record-identity fields |
| `explncc/record_identity.py` | `record_id`, `record_hash`, `raw_hash`, semantic/source keys |
| `explncc/summary.py` / `stats.py` | Filtering and aggregates |
| `explncc/diffing.py` | Build-vs-build missed deltas and counters |
| `explncc/report_diff.py` | Semantic optimization diff for CI (`report-diff`) |
| `explncc/exporters.py` | `json`, `jsonl`, `csv` |
| `explncc/checks.py` | Deterministic CI policy thresholds |
| `explncc/explain/` | Rule text, optional HTTP backends, `ExplanationResult`, on-device cache |
| `explncc/prompt_registry.py` | Versioned prompt templates and `prompt_hash` |
| `explncc/context_snippets.py` | Source / IR / assembly snippet extraction and asm signals |
| `explncc/evidence.py` | Evidence packs (the model-facing unit, `evidence_hash`) |
| `explncc/trace.py` | Pipeline trace for architecture visibility |
| `explncc/toolchains/` | Clang `.opt.yaml` and experimental HLS adapters (extensible boundary) |
| `explncc/records_loader.py` | Load records via a toolchain adapter |
| `explncc/html_report.py` | Standalone HTML reports with embedded CSS |
| `explncc/alignment.py` | Heuristic SIMD / alignment-related remark slice and labels |
| `explncc/alignment_pack.py` | Chapter 11 alignment evidence packs |
| `explncc/prompt_templates.py` | Named Chapter 11 user prompts (`minimal`, `guided`, `rubric`, ...) |
| `explncc/dataset_llm.py` | JSONL builders for training and bench rows |
| `explncc/ci_report.py` | Markdown / JSON / HTML / GitHub CI reports |
| `explncc/ci_manifest.py` | CI artifact manifest (`--write-manifest`, `ci-manifest`) |
| `explncc/report_types.py` | Stable JSON report schema and metadata types |
| `explncc/digest.py` | Per-file and aggregate SHA-256 over `.opt.yaml` inputs |
| `explncc/config.py` | Backend environment and the `doctor` payload |
| `explncc/viz.py` | Mermaid / HTML / JSON visualization bundles (`viz` command) |
| `explncc/local/` | Offline rule-based classifier and ranker (no network) |
| `explncc/cli.py` | Typer commands |

The subpackages stay small so a book chapter can point to one file at a time.

## Supported inputs

- Clang/LLVM `-fsave-optimization-record` / `-foptimization-record-file=…` output (`.opt.yaml`).
- A single file or a directory tree; only `*.opt.yaml` files are read.

## Limitations

- Heuristics depend on Clang's YAML shape. Newer LLVM versions may add fields, which are handled conservatively.
- The `alignment` slice is keyword and pass based, not semantic analysis. Validate it on your own corpus before publishing benchmark numbers.
- `diff` compares fingerprints of normalized rows, so identical logical events with different wording can look distinct.
- Context attachment needs a correct `--source-root` and external `.ll` / `.s` files. Wrong paths yield empty snippets, not invented code.
- Evidence and alignment packs list `missing_context` explicitly. The teachers and evaluators are conservative heuristics, not oracle labels.
- Model backends augment text only. They consume normalized records or packs, not raw `.opt.yaml`, and they never drive CI pass or fail.
- `dataset` and `bench-prompts` emit structure for training. They do not track your fine-tuning provider's latest JSONL schema, so check it against current API docs.
- `report` with explanation enabled can call remote model APIs. Prefer `--no-explain` on high-frequency CI unless you control the keys, quotas, and data-retention policy.

## Roadmap

- Deeper remark-specific extractors (more structured fields from `Args`).
- Optional SARIF or LSP-adjacent bridges.
- Tighter CI recipes (`explncc check` presets).

## For readers of *Decode the Compiler*

Use the bundled `examples/` to emit real `.opt.yaml` on your machine, then run explncc to connect source patterns to compiler vocabulary.

| Chapter | Doc |
|---------|-----|
| 10. LST, evidence packs, context | [chapter-10-notes.md](docs/chapter-10-notes.md) |
| 11. alignment pipeline, context, datasets | [chapter-11-alignment.md](docs/chapter-11-alignment.md), [chapter-11-notes.md](docs/chapter-11-notes.md) |
| 12. CI reports, semantic diff, gates | [chapter-12-ci.md](docs/chapter-12-ci.md), [chapter-12-notes.md](docs/chapter-12-notes.md) |
| 13. architecture, trace, digest | [architecture.md](docs/architecture.md), [chapter-13-notes.md](docs/chapter-13-notes.md) |
| 14. viz | [chapter-14-notes.md](docs/chapter-14-notes.md) |

## Why not just read `.opt.yaml` by hand?

You can, and you should once, to see the raw stream. explncc exists so you can filter, count, diff across builds, and export the same information reliably, for notes, for CI, and optionally for model-assisted prose.

## Design principles

1. Deterministic core first. Every command works without network access.
2. No invented fields. Missing data stays absent, and `args_raw` preserves the source.
3. AI as augmentation. Rule text is always available; HTTP backends only enrich labeled sections.
4. LST context leaves. Attach source, IR, or assembly when available; never fabricate a missing layer.
5. Semantic history. One `.opt.yaml` is an LST snapshot; sequences across builds support `report-diff` drift analysis.

## Optional model backends

The backends are `rule` (deterministic, offline, always available), `ollama` (local), `openai`, `claude`, and `auto` (try a configured model, fall back to rule on any failure). Select one with `--explain-backend` (or `--backend` on the `explain` command); set a default with `EXPLNCC_BACKEND`.

- Ollama (local): set `OLLAMA_HOST`, `OLLAMA_MODEL` (default `qwen2.5-coder:7b-instruct`).
- OpenAI: set `OPENAI_API_KEY`; optional `OPENAI_MODEL` (default `gpt-4o-mini`).
- Anthropic (Claude): set `ANTHROPIC_API_KEY`; optional `ANTHROPIC_MODEL` (default `claude-3-5-haiku-20241022`).

Set `EXPLNCC_NO_NETWORK` (or `EXPLNCC_OFFLINE`) to forbid every network backend. Set `EXPLNCC_CACHE_DIR` to enable the on-device explanation cache: a model-backed result is stored under a content-addressed key (evidence, prompt, backend, model, and explncc version), so an unchanged input is explained once and reused, and a stale explanation is never served. See [docs/model-backends.md](docs/model-backends.md).

## Local models are fast enough

The explanation job here is small by construction: the fusion layer hands the model the compiler's verdict, cause, and suggestion, and asks for two sentences and a next step, capped at 140 output tokens per finding. That is a job a 3B model does well and quickly, on hardware you already own, with evidence that never leaves the machine.

Measured with `explncc bench-backends` on a MacBook (Apple silicon, 16 GB), 3 missed findings from a real Clang 17 `.opt.yaml`:

| backend | model | mode | findings | total | per finding | note |
|---|---|---|---|---|---|---|
| rule | - | generate | 3 | 0.0s | 0.0s |  |
| ollama | qwen2.5-coder:3b | generate | 3 | 11.7s | 3.9s |  |
| ollama | qwen2.5-coder:3b | cached | 3 | 0.0s | 0.0s |  |
| ollama | mistral | generate | 3 | 27.6s | 9.2s |  |
| ollama | mistral | cached | 3 | 0.1s | 0.0s |  |

The cached rows are what a re-run after an unchanged build costs: the per-finding cache is content-addressed, so the second `why --explain` answers from disk. Numbers are wall-clock on one machine; run the same table on your own corpus:

```bash
explncc bench-backends build/ --backend rule --backend ollama \
  --ollama-model qwen2.5-coder:3b --format markdown
```

Backends without a server or key become explicit `skipped` rows rather than errors, so the table never silently overstates what ran.

## Building the book examples

```bash
brew install llvm   # macOS
make examples       # writes under build/examples/<name>/
```

Details: [docs/getting-started.md](docs/getting-started.md) and [docs/examples.md](docs/examples.md).

## Contributing

- `make check` runs ruff, the format check, mypy, and pytest.
- `make docs-check` confirms the required doc files are present.
- Prefer focused changes with tests beside `tests/fixtures/*.opt.yaml`.

## Development workflow

```bash
make install-dev
make check
make demo          # needs `make examples` first
make chapter11-demo PYTHON="$(pwd)/.venv/bin/python3"   # alignment + bench-prompts sample
make chapter12-demo PYTHON="$(pwd)/.venv/bin/python3"   # CI-style github report (fixture)
make chapter13-demo PYTHON="$(pwd)/.venv/bin/python3"   # trace, digest, doctor, HTML
```

### Testing the alignment pipeline

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

### Testing `report` / `report-diff`

```bash
python -m explncc report tests/fixtures/inline_miss_no_definition.opt.yaml --format markdown
python -m explncc report tests/fixtures/inline_miss_no_definition.opt.yaml --format github | head -n 20
python -m explncc report-diff tests/fixtures/inline_miss_no_definition.opt.yaml \
  tests/fixtures/inline_miss_no_definition.opt.yaml --format markdown
python -m pytest -q tests/test_ci_report.py tests/test_report_cli.py tests/test_chapter12_ci.py
```

## License

MIT
