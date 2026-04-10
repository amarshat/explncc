# CI integration examples (Chapter 12)

Copy these patterns into your own pipelines. explncc is **read-only** on `.opt.yaml`; your build job must still produce the optimization record file (see `docs/getting-started.md`).

| Path | Use |
|------|-----|
| [github-actions/explncc-report.yml](github-actions/explncc-report.yml) | GitHub Actions: job summary + optional thresholds |
| [jenkins/Jenkinsfile.snippet](jenkins/Jenkinsfile.snippet) | Jenkins: `sh` + archive HTML/Markdown |
| [cron/cron.example](cron/example.cron) | Local scheduler: one-line schedule |

Related docs: [docs/chapter-12-notes.md](../../docs/chapter-12-notes.md).
