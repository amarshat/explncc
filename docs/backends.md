# Explanation backends

See also [model-backends.md](model-backends.md) for environment variables.

## Contract

Backends **must**:

- Accept normalized record slices or evidence-derived JSON
- Use versioned prompts (`prompt_registry.py`)
- Return `ExplanationResult` with `prompt_hash` and `evidence_hash`

Backends **must not**:

- Read raw `.opt.yaml`
- Read arbitrary repository files
- Infer missing target triple / CPU details
- Change deterministic report or policy fields
- Affect CI pass/fail gates

## Modes

| Backend | Deterministic | Notes |
|---------|---------------|-------|
| `rule` | Yes | Always available, offline |
| `ollama` | No | Local HTTP |
| `openai` | No | Requires `OPENAI_API_KEY` |
| `claude` | No | Requires `ANTHROPIC_API_KEY` |
| `auto` | No | Ollama → Claude → OpenAI fallback chain |

## Failure behavior

- Default: fallback to rule text; warnings in report explanation block
- `--strict-explain`: exit non-zero on backend failure

## Caching

Explanation cache keys should include:

- `evidence_hash`
- `prompt_hash`
- backend name
- model name
- `explncc` version

See [caching-and-digest.md](caching-and-digest.md).
