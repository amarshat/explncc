"""Standalone HTML reports with embedded CSS (Chapter 13)."""

from __future__ import annotations

import html
import json
from typing import Any

from explncc.checks import PolicyResult
from explncc.ci_report import (
    _location_string,
    _normalize_whitespace,
    top_missed_remarks,
)
from explncc.models import OptimizationRecord
from explncc.report_types import (
    ExplanationInfo,
    ReportBuildOptions,
    ReportMetadata,
    ReportSourceInfo,
)
from explncc.stats import aggregate


def _esc(value: str | None) -> str:
    return html.escape(value or "")


def build_html_report_document(
    records: list[OptimizationRecord],
    *,
    source: ReportSourceInfo,
    metadata: ReportMetadata,
    options: ReportBuildOptions,
    policy: PolicyResult | None,
    explanation: ExplanationInfo,
    embed_json: bool = False,
    json_payload: dict[str, Any] | None = None,
) -> str:
    stats = aggregate(records)
    missed = top_missed_remarks(records, options.top_missed)
    policy_status = "pass" if policy is None or policy.ok else "fail"

    parts: list[str] = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "<meta charset='utf-8'/>",
        f"<title>{_esc(options.title)}</title>",
        "<style>",
        "body{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;line-height:1.5;color:#1a1a1a}",
        "h1,h2{border-bottom:1px solid #ddd;padding-bottom:.25rem}",
        "table{border-collapse:collapse;width:100%;margin:1rem 0}",
        "th,td{border:1px solid #ccc;padding:.4rem .6rem;text-align:left;vertical-align:top}",
        "th{background:#f5f5f5}",
        "pre{background:#f8f8f8;padding:.75rem;border-radius:3px;overflow-x:auto;white-space:pre-wrap}",
        ".notice{background:#f0f7ff;border:1px solid #c5dff8;padding:1rem;border-radius:4px}",
        ".warn{background:#fff8e6;border:1px solid #f0d080;padding:.75rem;border-radius:4px}",
        ".explain{border-left:4px solid #888;padding-left:1rem;margin:1rem 0}",
        "</style>",
        "</head>",
        "<body>",
        f"<h1>{_esc(options.title)}</h1>",
        "<h2>Build Metadata</h2>",
        "<ul>",
        f"<li><strong>Input:</strong> <code>{_esc(source.input_path)}</code></li>",
        f"<li><strong>Remarks:</strong> {source.remark_count} ({source.file_count} file(s))</li>",
    ]
    if metadata.git_sha:
        parts.append(f"<li><strong>Git SHA:</strong> <code>{_esc(metadata.git_sha)}</code></li>")
    if metadata.branch:
        parts.append(f"<li><strong>Branch:</strong> {_esc(metadata.branch)}</li>")
    parts.append("</ul>")

    parts.append("<h2>Summary</h2>")
    parts.append(f"<p><strong>Total remarks:</strong> {stats['total']}</p>")
    if stats.get("by_kind"):
        kinds = ", ".join(f"{_esc(k)}: {v}" for k, v in list(stats["by_kind"].items())[:8])
        parts.append(f"<p><strong>By kind:</strong> {kinds}</p>")

    parts.append("<h2>Policy</h2>")
    if policy is None:
        parts.append("<p><em>No deterministic policy thresholds configured.</em></p>")
    else:
        parts.append(f"<p><strong>Status:</strong> {_esc(policy_status)}</p>")
        if not policy.ok:
            parts.append("<ul>")
            for t in policy.thresholds:
                if not t.ok:
                    parts.append(
                        f"<li><code>{_esc(t.name)}</code>: actual {t.actual} &gt; limit {t.limit}</li>",
                    )
            parts.append("</ul>")

    parts.append("<h2>Top Missed Optimizations</h2>")
    if not missed:
        parts.append("<p><em>No missed remarks in this slice.</em></p>")
    else:
        parts.append(
            "<table><thead><tr><th>Pass</th><th>Remark</th><th>Function</th>"
            "<th>Location</th><th>Message</th></tr></thead><tbody>",
        )
        for r in missed:
            msg = _normalize_whitespace(r.message)
            if len(msg) > options.message_max_chars:
                msg = msg[: options.message_max_chars - 1] + "…"
            parts.append(
                "<tr>"
                f"<td><code>{_esc(r.pass_name)}</code></td>"
                f"<td><code>{_esc(r.remark_name)}</code></td>"
                f"<td><code>{_esc(r.function)}</code></td>"
                f"<td><code>{_esc(_location_string(r))}</code></td>"
                f"<td><pre>{_esc(msg)}</pre></td>"
                "</tr>",
            )
        parts.append("</tbody></table>")

    if explanation.enabled and explanation.items:
        label = _esc(explanation.label or "Optional interpretation")
        parts.append(f"<h2>{label}</h2>")
        if explanation.warning:
            parts.append(f'<div class="warn"><strong>Warning:</strong> {_esc(explanation.warning)}</div>')
        for item in explanation.items:
            parts.append(f'<div class="explain"><pre>{_esc(item.get("text", "").strip())}</pre></div>')

    parts.append('<h2>Raw Artifact Notice</h2>')
    parts.append(
        '<div class="notice"><p>The <code>.opt.yaml</code> file remains the source of truth. '
        "This HTML report summarizes normalized compiler evidence. "
        "Interpretation sections are assistive only when present.</p></div>",
    )

    if embed_json and json_payload is not None:
        payload = json.dumps(json_payload, ensure_ascii=False)
        parts.append(
            f'<script type="application/json" id="explncc-report">{_esc(payload)}</script>',
        )

    parts.extend(["</body>", "</html>"])
    return "\n".join(parts)
