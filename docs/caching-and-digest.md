# Caching and digest

`explncc digest` hashes **compiler evidence** (`.opt.yaml` files), not binaries.

## Basic digest

```bash
python -m explncc digest build/examples/
```

Returns per-file SHA-256, record counts, aggregate `cache_key`.

## Evidence-aware digest

```bash
python -m explncc digest build/examples/ --include-evidence
```

Adds `evidence_aggregate_hash` and `recommended_cache_key`.

## Prompt-aware digest

```bash
python -m explncc digest build/app.opt.yaml \
  --include-prompts --template guided
```

Includes prompt template hash for explanation cache invalidation.

## Recommended explanation cache key

When caching model explanations, combine:

- `evidence_hash` (from evidence packs)
- `prompt_hash` (from `prompt_registry`)
- backend name (`rule`, `openai`, …)
- model name (e.g. `gpt-4o-mini`)
- `explncc_version`

`digest` output field `recommended_cache_key` aggregates file + record + optional evidence/prompt hashes.

## CI usage

Use digest to skip re-running expensive steps when optimization logs are unchanged:

```yaml
- run: python -m explncc digest build/ -o digest.json
- uses: actions/cache@v4
  with:
    key: explncc-${{ hashFiles('digest.json') }}
```

Note: identical `.opt.yaml` with different binaries still yields the same digest — that is intentional for remark-level caching.
