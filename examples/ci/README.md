# CI integration examples (Chapter 12)

Copy these patterns into your own pipelines. explncc is **read-only** on `.opt.yaml`; your build job must still produce the optimization record file (see `docs/getting-started.md`).

| Path | Use |
|------|-----|
| [github-actions/explncc-report.yml](github-actions/explncc-report.yml) | Step summary + JSON + PR comment artifact |
| [github-actions/explncc-gated.yml](github-actions/explncc-gated.yml) | Deterministic `--fail-on-check` gate |
| [github-actions/explncc-diff-pr.yml](github-actions/explncc-diff-pr.yml) | Semantic `report-diff` for PRs |
| [jenkins/Jenkinsfile.snippet](jenkins/Jenkinsfile.snippet) | Markdown + JSON + gate + archive |
| [cron/run_nightly_report.sh](cron/run_nightly_report.sh) | Timestamped nightly archive |

Related docs: [docs/chapter-12-ci.md](../../docs/chapter-12-ci.md).
