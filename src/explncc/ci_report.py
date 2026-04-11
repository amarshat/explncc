"""CI-oriented reports: Markdown, JSON, HTML, and GitHub-flavored snippets.

These builders are deterministic except when the caller passes pre-rendered
``explain_text`` from an optional model backend.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any, Literal

from explncc.checks import CheckResult
from explncc.exporters import record_to_json_dict
from explncc.models import OptimizationRecord
from explncc.stats import aggregate

ReportFormat = Literal["markdown", "json", "github", "html"]


def parse_report_format(value: str) -> ReportFormat:
    """Parse CLI ``--format`` into a :class:`ReportFormat`."""

    v = value.strip().lower()
    if v == "markdown":
        return "markdown"
    if v == "json":
        return "json"
    if v == "github":
        return "github"
    if v == "html":
        return "html"
    msg = f"unknown report format: {value!r}"
    raise ValueError(msg)


def _normalize_whitespace(text: str | None) -> str:
    """Collapse runs of whitespace (common when YAML ``Args`` strings are joined)."""

    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _location_string(record: OptimizationRecord) -> str:
    """``file:line:column`` when present; never mid-path ellipsis."""

    if not record.file:
        return "—"
    loc = record.file
    if record.line is not None:
        loc += f":{record.line}"
        if record.column is not None:
            loc += f":{record.column}"
    return loc


def _missed_remarks_markdown_sections(
    missed: list[OptimizationRecord],
    *,
    message_max_chars: int = 4000,
) -> list[str]:
    """Readable Markdown blocks (no wide tables) for missed remark lists."""

    lines: list[str] = []
    for i, r in enumerate(missed, start=1):
        pname = r.pass_name or "—"
        rname = r.remark_name or "—"
        lines.append(f"#### {i}. `{pname}` / `{rname}`")
        lines.append("")
        lines.append(f"- **Function:** `{r.function or '—'}`")
        lines.append(f"- **Where:** `{_location_string(r)}`")
        lines.append("")
        lines.append("**Compiler message:**")
        lines.append("")
        msg = _normalize_whitespace(r.message)
        if msg:
            body = msg if len(msg) <= message_max_chars else msg[: message_max_chars - 1] + "…"
            lines.append("```text")
            lines.append(body)
            lines.append("```")
        else:
            lines.append("_No message text after normalization._")
        lines.append("")
    return lines


def top_missed_remarks(records: list[OptimizationRecord], limit: int) -> list[OptimizationRecord]:
    """Return up to ``limit`` missed remarks in file order."""

    missed = [r for r in records if r.kind == "missed"]
    return missed[:limit] if limit > 0 else missed


def build_json_payload(
    records: list[OptimizationRecord],
    *,
    top_missed: int,
    check_result: CheckResult | None,
    explain_text: str | None,
    title: str,
) -> dict[str, Any]:
    """Structured report for APIs, artifacts, and downstream PR bots."""

    stats = aggregate(records)
    missed = top_missed_remarks(records, top_missed)
    payload: dict[str, Any] = {
        "title": title,
        "stats": stats,
        "top_missed": [record_to_json_dict(r) for r in missed],
        "check": (
            {"ok": check_result.ok, "violations": check_result.violations}
            if check_result is not None
            else None
        ),
        "explain": explain_text,
    }
    return payload


def build_markdown_report(
    records: list[OptimizationRecord],
    *,
    top_missed: int,
    check_result: CheckResult | None,
    explain_text: str | None,
    title: str,
) -> str:
    """Full Markdown report (CI logs, wikis, ``GITHUB_STEP_SUMMARY``)."""

    stats = aggregate(records)
    lines: list[str] = [f"# {title}", ""]
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total remarks:** {stats['total']}")
    if stats.get("by_kind"):
        kinds = ", ".join(f"{k}: {v}" for k, v in list(stats["by_kind"].items())[:8])
        lines.append(f"- **By kind:** {kinds}")
    lines.append("")

    if check_result is not None:
        lines.append("## Policy check")
        lines.append("")
        if check_result.ok:
            lines.append("**Status:** PASS")
        else:
            lines.append("**Status:** FAIL")
            for v in check_result.violations:
                lines.append(f"- {v}")
        lines.append("")

    lines.append("## Top missed optimizations")
    lines.append("")
    missed = top_missed_remarks(records, top_missed)
    if not missed:
        lines.append("_No missed remarks in this slice._")
    else:
        lines.extend(_missed_remarks_markdown_sections(missed))
    lines.append("")

    if explain_text:
        lines.append("## Explanation")
        lines.append("")
        lines.append(explain_text.strip())
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "_Generated by explncc — compiler remarks are authoritative; explanations are assistive._",
    )
    return "\n".join(lines)


def build_html_report(
    records: list[OptimizationRecord],
    *,
    top_missed: int,
    check_result: CheckResult | None,
    explain_text: str | None,
    title: str,
) -> str:
    """Self-contained HTML for browsers, wikis, or email attachments."""

    stats = aggregate(records)
    missed = top_missed_remarks(records, top_missed)
    esc = html.escape
    lines: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8"/>',
        f"<title>{esc(title)}</title>",
        "<style>",
        "body{font-family:system-ui,sans-serif;max-width:56rem;margin:1.5rem auto;"
        "line-height:1.45;color:#111}",
        "pre{background:#f6f8fa;padding:0.75rem;overflow:auto;border:1px solid #d0d7de;"
        "border-radius:6px;white-space:pre-wrap}",
        "h1,h2,h4{border-bottom:1px solid #eee;padding-bottom:0.2rem}",
        "</style>",
        "</head><body>",
        f"<h1>{esc(title)}</h1>",
        "<h2>Summary</h2>",
        "<ul>",
        f"<li><strong>Total remarks:</strong> {stats['total']}</li>",
    ]
    if stats.get("by_kind"):
        kinds = ", ".join(f"{esc(str(k))}: {v}" for k, v in list(stats["by_kind"].items())[:8])
        lines.append(f"<li><strong>By kind:</strong> {kinds}</li>")
    lines.append("</ul>")

    if check_result is not None:
        lines.append("<h2>Policy check</h2>")
        if check_result.ok:
            lines.append("<p><strong>Status:</strong> PASS</p>")
        else:
            lines.append("<p><strong>Status:</strong> FAIL</p><ul>")
            for v in check_result.violations:
                lines.append(f"<li>{esc(v)}</li>")
            lines.append("</ul>")

    lines.append("<h2>Top missed optimizations</h2>")
    if not missed:
        lines.append("<p><em>No missed remarks in this slice.</em></p>")
    else:
        for i, r in enumerate(missed, start=1):
            pname = esc(r.pass_name or "—")
            rname = esc(r.remark_name or "—")
            lines.append(
                f"<section><h4>{i}. <code>{pname}</code> / <code>{rname}</code></h4>",
            )
            lines.append("<ul>")
            fn_esc = esc(r.function or "—")
            lines.append(f"<li><strong>Function:</strong> <code>{fn_esc}</code></li>")
            loc_esc = esc(_location_string(r))
            lines.append(f"<li><strong>Where:</strong> <code>{loc_esc}</code></li>")
            lines.append("</ul>")
            lines.append("<p><strong>Compiler message:</strong></p>")
            msg = _normalize_whitespace(r.message)
            if msg:
                body = msg if len(msg) <= 4000 else msg[:3999] + "…"
                lines.append(f"<pre>{esc(body)}</pre>")
            else:
                lines.append("<p><em>No message text after normalization.</em></p>")
            lines.append("</section>")

    if explain_text:
        lines.append("<h2>Explanation</h2>")
        lines.append(f"<pre>{esc(explain_text.strip())}</pre>")

    lines.append("<hr/>")
    lines.append(
        "<p><em>Generated by explncc — compiler remarks are authoritative; "
        "explanations are assistive.</em></p>",
    )
    lines.append("</body></html>")
    return "\n".join(lines)


def build_github_comment(
    records: list[OptimizationRecord],
    *,
    top_missed: int,
    check_result: CheckResult | None,
    explain_text: str | None,
    title: str,
) -> str:
    """Compact Markdown for PR comments (collapsible detail for long lists)."""

    stats = aggregate(records)
    status = "✅" if (check_result is None or check_result.ok) else "❌"
    lines: list[str] = [
        f"### {status} {title}",
        "",
        f"**Remarks:** {stats['total']} total",
    ]
    if check_result is not None and not check_result.ok:
        lines.append("")
        lines.append("**Check violations:**")
        for v in check_result.violations:
            lines.append(f"- {v}")

    missed = top_missed_remarks(records, top_missed)
    lines.append("")
    lines.append(f"<details><summary><strong>Top {len(missed)} missed</strong> (expand)</summary>")
    lines.append("")
    if not missed:
        lines.append("_None._")
    else:
        lines.extend(_missed_remarks_markdown_sections(missed))
    lines.append("")
    lines.append("</details>")
    lines.append("")

    if explain_text:
        lines.append("<details><summary><strong>Explanation</strong> (rule / model)</summary>")
        lines.append("")
        lines.append(explain_text.strip())
        lines.append("")
        lines.append("</details>")
        lines.append("")

    return "\n".join(lines)


def render_report(
    fmt: ReportFormat,
    records: list[OptimizationRecord],
    *,
    top_missed: int,
    check_result: CheckResult | None,
    explain_text: str | None,
    title: str,
) -> str:
    """Dispatch to the requested string format."""

    if fmt == "json":
        payload = build_json_payload(
            records,
            top_missed=top_missed,
            check_result=check_result,
            explain_text=explain_text,
            title=title,
        )
        return json.dumps(payload, indent=2, ensure_ascii=False)
    if fmt == "github":
        return build_github_comment(
            records,
            top_missed=top_missed,
            check_result=check_result,
            explain_text=explain_text,
            title=title,
        )
    if fmt == "html":
        return build_html_report(
            records,
            top_missed=top_missed,
            check_result=check_result,
            explain_text=explain_text,
            title=title,
        )
    return build_markdown_report(
        records,
        top_missed=top_missed,
        check_result=check_result,
        explain_text=explain_text,
        title=title,
    )
