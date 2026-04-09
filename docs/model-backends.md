# Explanation backends

`explncc explain` always starts from **normalized** optimization records (never raw YAML). Deterministic **rule-based** text is the default and the fallback if a model backend errors.

## Backends

| Mode | When it runs | Requirements |
|------|----------------|--------------|
| `rule` | Default; explicit `--backend rule` | None |
| `ollama` | `--backend ollama` or `EXPLNCC_BACKEND=ollama` | Ollama listening on `OLLAMA_HOST` (default `http://127.0.0.1:11434`), model pulled |
| `openai` | `--backend openai` | `OPENAI_API_KEY` set |
| `auto` | `--backend auto` | Try Ollama (quick probe), else OpenAI if key present, else `rule` |

## Environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `EXPLNCC_BACKEND` | Default backend if CLI omits `--backend` | `rule` |
| `OLLAMA_HOST` | Ollama API base URL | `http://127.0.0.1:11434` |
| `OLLAMA_MODEL` | Model tag for `/api/chat` | `qwen2.5-coder:7b-instruct` |
| `OPENAI_API_KEY` | Bearer token for OpenAI | unset |
| `OPENAI_MODEL` | Chat model name | `gpt-4o-mini` |

## Default local model: `qwen2.5-coder:7b-instruct`

Instruction-tuned code models tend to stay closer to compiler vocabulary than general chat models. The 7B size is a practical default for laptops while still handling structured prompts. **Mistral** (`mistral:7b-instruct`) is a reasonable alternative if you prefer it—set `OLLAMA_MODEL` accordingly.

## Grounding

AI backends receive:

- A short system instruction: augment only; do not invent passes, functions, or file paths.
- JSON-serialized slices of normalized records (pass, kind, function, reason, message, location).

If the HTTP call fails or returns empty content, explncc prints the rule-based explanation.
