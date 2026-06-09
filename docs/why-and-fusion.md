# `why`, fusion, and the per-finding explain path

## The problem `why` solves

One compiler decision lands in `.opt.yaml` as several records. A missed
vectorization is a `!Missed` rollup ("loop not vectorized") plus a sibling
`!Analysis` record carrying the actual cause ("Backward loop carried data
dependence"). SLP emits near-identical records per instruction bundle at the
same location. Read record-by-record, a tool either punts on the cause or
repeats itself. `fusion.py` groups the records back into one finding per
decision; `why` renders that finding.

## Fusion rules (`src/explncc/fusion.py`)

- Noise passes (`asm-printer`, `prologepilog`, `size-info`, `annotation`) are
  dropped unless `include_noise=True` (`--all` on the CLI).
- Exact duplicates (same kind, pass, remark, function, location, message)
  fold into one finding with a `count`.
- A `missed` record absorbs `analysis` records of the same pass, same
  function, same file, within 3 lines. The analysis message becomes the
  finding's `cause`; a `Use ...` sentence inside it is extracted verbatim as
  the `suggestion`; the analysis column becomes the caret column.
- Headlines are short labels over compiler fields, never paraphrases of the
  message: `not vectorized: loop-carried dependence`,
  `not inlined: cost 815 > threshold 812`,
  `SLP not beneficial (cost 0 >= threshold 0)`,
  `II target missed (achieved 3 vs target 1)`.
- Findings sort by severity: vectorization and HLS misses, then inline, SLP,
  other misses, spills, analysis notes, and finally passed records.

Function names are demangled in batch through `c++filt` or `llvm-cxxfilt`
(`src/explncc/demangle.py`). No demangler, a crash, or mismatched output all
degrade to the mangled name.

## `why` usage

```bash
explncc why build/                  # triage a records directory
explncc why hot.cpp:42              # one location; records auto-discovered under .
explncc why scan                    # function-name substring
explncc why build/ --missed-only    # only real misses (spills are NOTE tier)
explncc why build/ --all --top 0    # everything, including noise
```

`--missed-only` filters by the MISS verdict tag, not the raw YAML tag:
regalloc spill statistics arrive as `!Missed` records but are notes, not
actionable misses.

When the first argument is a query rather than a records path, `why` searches
the current directory recursively for `*.opt.yaml` (skipping VCS and
virtualenv directories). If none exist it prints the exact compile flag to
generate them and exits 2.

## `--explain`: the per-finding short path

`why --explain` adds a short model note under each MISS finding (cap 5):

- the prompt is the fused evidence (verdict, cause, suggestion), so the model
  phrases and suggests rather than re-derives;
- output is capped at 140 tokens; Ollama responses stream as they generate;
- each finding is cached individually under a content-addressed key
  (records + prompt + backend + model + version) when `EXPLNCC_CACHE_DIR` is
  set, so a re-run after an unchanged build answers from disk;
- any backend failure falls back to the deterministic evidence text, never an
  error;
- a summary line goes to stderr:
  `[explain] 3 findings in 9.3s with qwen2.5-coder:3b on-device: 3 generated,
  0 cached; nothing left this machine`.

Backends: `ollama` (default, local), `openai`, `claude`, `rule`
(deterministic text, no model). `--model` overrides the model tag.
`--no-network` and `EXPLNCC_NO_NETWORK` refuse network backends with exit 2.

## `bench-backends`

```bash
explncc bench-backends build/ --backend rule --backend ollama \
  --ollama-model qwen2.5-coder:3b --format markdown
```

Runs the same fused findings through each backend's per-finding path and
reports wall-clock per finding. Generation is measured without a cache; a
`cached` row per model times a primed replay. Unreachable servers, unpulled
models, missing API keys, and the no-network guardrail all become explicit
`skipped` rows.

## Relationship to `explain`

`explain` remains the batch path: rule paragraphs over many records, with
optional whole-batch model augmentation, used by `report`. `why --explain` is
the interactive path: per-decision evidence, short outputs, streaming, and
per-finding caching. Both honor the same guardrails and the same cache
directory.
