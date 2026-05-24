# Chapter 13 — Architecture workflows

Deterministic compiler-semantic infrastructure demos (no model API calls required).

## 1. Trace the pipeline

```bash
python -m explncc trace tests/fixtures/simd_vectorized.opt.yaml \
  --format markdown \
  --include-sample-record \
  --include-evidence \
  -o build/chapter13/trace.md
```

## 2. Digest compiler evidence

```bash
python -m explncc digest tests/fixtures/ \
  --include-evidence
```

With prompt template hash:

```bash
python -m explncc digest tests/fixtures/simd_vectorized.opt.yaml \
  --include-prompts --template guided
```

## 3. Doctor (masked config)

```bash
python -m explncc doctor --format markdown
```

## 4. HTML report (standalone, embedded CSS)

```bash
mkdir -p build/chapter13
python -m explncc report tests/fixtures/simd_vectorized.opt.yaml \
  --format html \
  --embed-json \
  -o build/chapter13/report.html
```

## 5. JSON systems report

```bash
python -m explncc report tests/fixtures/simd_vectorized.opt.yaml \
  --format json \
  -o build/chapter13/report.json
```

## 6. Explain (deterministic rule backend)

```bash
python -m explncc explain tests/fixtures/inline_miss_no_definition.opt.yaml \
  --backend rule
```

## 7. Explain (auto with safe fallback)

```bash
python -m explncc explain tests/fixtures/inline_miss_no_definition.opt.yaml \
  --backend auto
```

## Report format comparison

| Format | Command flag | Consumer |
|--------|--------------|----------|
| Markdown | `--format markdown` | docs, step summaries |
| JSON | `--format json` | dashboards, bots |
| GitHub | `--format github` | PR comment bodies |
| HTML | `--format html` | browser, attachments |

See [docs/architecture.md](../../docs/architecture.md) for the full module map.
