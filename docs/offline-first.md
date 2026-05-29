# Offline-First

explncc works **offline by default**. The core workflow — parse `.opt.yaml`,
normalize, classify, rank, explain, report — requires no network, no API keys,
no hosted LLM, no Ollama, and no external model server.

## Principles

- **explncc works offline by default.** Every core command (`classify`,
  `rank`, `explain --local`, `report --local`, `export-training`) runs with no
  network access.
- **LLMs are optional.** Model backends (OpenAI, Claude, Ollama) are an
  *augmentation* you opt into explicitly with `--backend`. They are never
  required and never the default for the local path.
- **Local mode uses rules + ranker + templates.** Intelligence in offline mode
  comes from a rule-based classifier, a deterministic weighted ranker, and
  template explanations drawn from the label taxonomy.
- **The ranker scores developer relevance, not absolute truth.** A high score
  means "likely worth a developer's attention", not "definitely a bug".
- **Compiler evidence remains authoritative.** The `.opt.yaml` file is the
  source of truth. Local labels and scores are heuristics on top of it.
- **Model backends are explanation-only.** They can rephrase or expand an
  explanation; they never override compiler facts or local classification.
- **No network in `--offline` mode.** `--offline` implies `--local` and refuses
  to call any network backend.

## Flags

| Flag | Meaning |
|------|---------|
| `--local` | Use the local deterministic pipeline (classifier + ranker + templates). No hosted backend, no Ollama. |
| `--offline` | Alias for `--local` that additionally **fails** if a network backend is requested. |
| `--no-network` | Guardrail: prevents any OpenAI/Claude/Ollama/auto HTTP call. |

Environment equivalents: set `EXPLNCC_NO_NETWORK=1` (or `EXPLNCC_OFFLINE=1`) to
enforce no-network globally. `EXPLNCC_BACKEND=local` makes local the default
for `explain`.

## Defaults

- `explain` defaults to the deterministic rule/local path unless a backend is
  explicitly requested.
- `report` defaults to no explanation (CI-safe); `report --local` adds local
  intelligence with no AI section.
- CI examples should use `--local` (or `--no-explain`).
- Hosted LLMs require an explicit `--backend openai` / `--backend claude`.

## Demo flow (no network required)

```bash
explncc classify build/app.opt.yaml --local --format table
explncc rank build/app.opt.yaml --local --top 10 --format markdown -o ranked.md
explncc explain build/app.opt.yaml --local
explncc report build/app.opt.yaml --local --format markdown -o report.md
explncc export-training build/app.opt.yaml \
  --include-labels-from rules --format jsonl -o training.jsonl
```

This fails safely (exit code 2, no HTTP call):

```bash
explncc explain build/app.opt.yaml --offline --backend openai
# Error: --offline forbids network/model backend 'openai'; use --backend rule / --local.
```

## See also

- [local-mode.md](local-mode.md) — the local pipeline and commands.
- [local-ranker.md](local-ranker.md) — feature extraction, scoring, tuning.
- [classifier-labels.md](classifier-labels.md) — every local label defined.
