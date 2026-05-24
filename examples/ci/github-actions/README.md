# GitHub Actions examples (Chapter 12)

Copy workflows into `.github/workflows/`.

| File | Purpose |
|------|---------|
| `explncc-report.yml` | Step summary, JSON artifact, PR comment body — **no model backend** |
| `explncc-gated.yml` | Deterministic `--fail-on-check` gate; uploads `gate.md` on failure |
| `explncc-diff-pr.yml` | `report-diff` baseline vs PR; semantic drift comment |

All examples default to `--no-explain`. Post PR comments with `gh pr comment --body-file pr-comment.md` or your bot.

See [docs/chapter-12-ci.md](../../../docs/chapter-12-ci.md).
