# Report formats

All formats consume the same normalized records and optional policy/explanation metadata.

| Format | CLI | Primary consumer |
|--------|-----|------------------|
| `markdown` | `--format markdown` | GitHub step summary, wiki, email |
| `json` | `--format json` | Dashboards, bots (`schema_version` stable) |
| `github` | `--format github` | PR comment bodies (`<details>` sections) |
| `html` | `--format html` | Browser, attachments (standalone CSS) |

## HTML options

```bash
python -m explncc report build/app.opt.yaml \
  --format html \
  --embed-json \
  -o report.html
```

- Escapes compiler messages and titles
- Sections: Build Metadata, Summary, Policy, Top Missed, optional labeled explanation, Raw Artifact Notice
- `--embed-json` adds `<script type="application/json">` block (escaped)

## Explanation labeling

When explanation is enabled, sections are titled **Rule-based interpretation** or **AI-assisted interpretation**. They never appear as the reason for policy failure.

## Artifacts vs source of truth

Reports summarize evidence. The `.opt.yaml` file (and JSON export) remain authoritative.
