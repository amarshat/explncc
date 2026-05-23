"""Render alignment evaluation reports."""

from __future__ import annotations

import json

from explncc.alignment_eval import EvalReport


def render_eval_report(report: EvalReport, fmt: str) -> str:
    fmt_l = fmt.strip().lower()
    if fmt_l == "json":
        return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
    if fmt_l == "markdown":
        return _render_markdown(report)
    msg = f"unknown eval format: {fmt!r} (expected json, markdown)"
    raise ValueError(msg)


def _render_markdown(report: EvalReport) -> str:
    parts: list[str] = [
        "# Alignment evaluation report\n\n",
        f"- **samples:** {len(report.samples)}\n",
        f"- **aggregate score:** {report.aggregate_score:.2f}\n\n",
    ]

    if report.failure_categories:
        parts.append("## Failure categories\n\n")
        for cat, count in sorted(report.failure_categories.items()):
            parts.append(f"- `{cat}`: {count}\n")
        parts.append("\n")

    if report.overreach_examples:
        parts.append("## Overreach examples\n\n")
        for ex in report.overreach_examples:
            parts.append(f"- {ex}\n")
        parts.append("\n")

    parts.append("## Per-sample scores\n\n")
    for sample in report.samples:
        parts.append(f"### {sample.sample_id}\n\n")
        parts.append(f"- total: **{sample.total:.1f}**\n")
        parts.append(f"- evidence_fidelity: {sample.evidence_fidelity}/2\n")
        parts.append(f"- alignment_discipline: {sample.alignment_discipline}/2\n")
        parts.append(f"- missing_context_awareness: {sample.missing_context_awareness}/2\n")
        parts.append(f"- next_step_quality: {sample.next_step_quality}/2\n")
        parts.append(f"- overreach_penalty: {sample.overreach_penalty}\n")
        parts.append(f"- conciseness: {sample.conciseness}/1\n")
        if sample.failure_categories:
            parts.append(f"- failure_categories: {', '.join(sample.failure_categories)}\n")
        parts.append("\n")

    return "".join(parts).rstrip() + "\n"
