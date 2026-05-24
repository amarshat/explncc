# Notes for Chapter 12 (LLM layer in compiler CI)

Chapter outline: *Adding an LLM Layer to Your Compiler CI* — GitHub Actions, Jenkins, cron, PR comments, and trustworthy automation.

## What explncc adds for this chapter

| Heading | Reader learns to DO | explncc support |
|---------|---------------------|-----------------|
| **Where in CI to intercept logs** | Choose the job that already has `.opt.yaml` (post-compile) or upload it as an artifact | No magic hook: document **after** `clang++` with `-foptimization-record-file`. |
| **Piping into AI-explain pipelines** | Wire stdout/files into summarization | `explncc report` with `--explain-backend rule\|ollama\|openai\|auto` (omit `--no-explain`). |
| **Output formats** | Pick Markdown vs JSON vs PR-friendly Markdown | `--format markdown` (logs, wiki, `GITHUB_STEP_SUMMARY`), `--format json` (bots, dashboards), `--format github` (collapsible PR bodies). |
| **Annotating PRs** | Post structured comments without spamming | Generate `pr-comment.md` with `--format github`; upload artifact or `gh pr comment --body-file`. |
| **Triage failures** | Fail builds on policy + show reasons | `report ... --fail-on-check --max-missed-inline N` (or loop-vectorize cap). Same thresholds as `explncc check`. |

## Trust and limitations (say this in prose)

- **Compiler YAML is authoritative**; reports and models **assist** triage.
- **`--fail-on-check`** uses the same simple counters as `check` — not full static analysis.
- **Secrets**: never log `OPENAI_API_KEY`; use provider OIDC or encrypted secrets.
- **Cost/latency**: use `--no-explain` on every push; enable model backends on nightly or labeled PRs only.

## Example commands (copy into the book)

```bash
# Job summary (GitHub Actions): see scripts/ci_github_step_summary.sh
python -m explncc report build/app.opt.yaml --format markdown --no-explain >> "$GITHUB_STEP_SUMMARY"

# JSON artifact for a dashboard or custom bot
python -m explncc report build/app.opt.yaml --format json --no-explain -o report.json

# PR comment body (collapsible sections)
python -m explncc report build/app.opt.yaml --format github --top-missed 10 -o pr-comment.md

# Gate + human-readable artifact
python -m explncc report build/app.opt.yaml -o gate.md --fail-on-check --max-missed-inline 80
```

## Repository samples

- [docs/chapter-12-ci.md](../../docs/chapter-12-ci.md) — full CI feedback loop guide (trust model, gates, semantic diff)
- `examples/ci/github-actions/explncc-report.yml` — Actions workflow template
- `examples/ci/github-actions/explncc-gated.yml` — deterministic policy gate
- `examples/ci/github-actions/explncc-diff-pr.yml` — semantic `report-diff` for PRs
- `examples/ci/jenkins/Jenkinsfile.snippet` — Declarative stage fragment
- `examples/ci/cron/` — `example.cron` + `run_nightly_report.sh`

## Skills ↔ chapter outcomes

1. **Automate log analysis** — `report` + cron/Jenkins/Actions.
2. **Integrate into PR review** — `github` format + artifact + `gh`/bot.
3. **Configure prompt pipelines** — `report` shares backends with `explain`; tune `--explain-limit` / `--ai-limit`.
4. **Actionable reports per commit** — title with `${{ github.sha }}` / `${BUILD_NUMBER}`; attach JSON + Markdown.
5. **Developer trust** — deterministic sections first; label model sections; keep `--no-explain` path for no-network CI.
