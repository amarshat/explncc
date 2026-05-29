"""Deterministic local intelligence report (offline, no AI section).

Builds a structured report from the local classifier + ranker and renders it as
markdown or JSON. No network, no model backend. An AI/model explanation section
is only ever added by callers that explicitly request a model backend.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from explncc.local.ranker import LocalRankerV1, RankedFinding
from explncc.local.taxonomy import get_label
from explncc.models import OptimizationRecord

LOCAL_REPORT_FORMATS = ("markdown", "json")


@dataclass
class LocalReport:
    title: str
    total: int
    by_kind: dict[str, int]
    by_label: dict[str, int]
    top_findings: list[RankedFinding]
    recommended_actions: list[str]
    evidence_refs: list[str] = field(default_factory=list)
    policy: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "total": self.total,
            "by_kind": self.by_kind,
            "by_label": self.by_label,
            "policy": self.policy,
            "top_findings": [f.to_dict() for f in self.top_findings],
            "recommended_actions": self.recommended_actions,
            "evidence_refs": self.evidence_refs,
        }


def build_local_report(
    records: list[OptimizationRecord],
    *,
    title: str = "Local Compiler Optimization Report",
    top: int = 12,
    include_passed: bool = False,
    focus: str | None = None,
    policy: dict[str, Any] | None = None,
) -> LocalReport:
    ranker = LocalRankerV1(include_passed=include_passed, focus=focus)
    findings = ranker.rank_records(records)

    by_kind: Counter[str] = Counter((r.kind or "unknown") for r in records)
    by_label: Counter[str] = Counter(f.label for f in findings)

    top_findings = findings[:top] if top > 0 else findings

    actions: list[str] = []
    for f in top_findings:
        for a in f.recommended_actions:
            if a not in actions:
                actions.append(a)

    evidence_refs: list[str] = []
    for f in top_findings:
        if f.record is not None and f.record.source_path:
            ref = f.record.source_path
            if ref not in evidence_refs:
                evidence_refs.append(ref)

    return LocalReport(
        title=title,
        total=len(records),
        by_kind=dict(by_kind),
        by_label=dict(by_label),
        top_findings=top_findings,
        recommended_actions=actions,
        evidence_refs=evidence_refs,
        policy=policy,
    )


def _loc(record: OptimizationRecord) -> str:
    parts: list[str] = []
    if record.file:
        parts.append(record.file)
    if record.line is not None:
        parts.append(str(record.line))
    return ":".join(parts) if parts else ""


def render_local_report(report: LocalReport, fmt: str) -> str:
    fmt = fmt.strip().lower()
    if fmt == "json":
        return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
    if fmt == "markdown":
        return _render_markdown(report)
    raise ValueError(f"unsupported local report format: {fmt!r}")


def _render_markdown(report: LocalReport) -> str:
    lines: list[str] = [f"# {report.title}", ""]

    # 1. Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- total remarks: {report.total}")
    for kind, count in sorted(report.by_kind.items()):
        lines.append(f"- {kind}: {count}")
    lines.append("")

    # 2. Policy (optional)
    if report.policy is not None:
        lines.append("## Policy")
        lines.append("")
        status = report.policy.get("status")
        lines.append(f"- status: {status if status is not None else 'unknown'}")
        for failure in report.policy.get("failures", []) or []:
            lines.append(f"- {failure}")
        lines.append("")

    # 3. Top ranked findings
    lines.append("## Top ranked findings")
    lines.append("")
    if not report.top_findings:
        lines.append("_No findings._")
    else:
        for f in report.top_findings:
            record = f.record
            lines.append(f"### {f.rank}. {f.label} (score {f.score:g}, {f.severity})")
            lines.append("")
            lines.append(f"- confidence: {f.confidence}")
            if record is not None:
                lines.append(f"- pass: {record.pass_name or '?'}")
                lines.append(f"- kind: {record.kind or '?'}")
                if record.function:
                    lines.append(f"- function: {record.function}")
                loc = _loc(record)
                if loc:
                    lines.append(f"- location: {loc}")
            if f.score_reasons:
                lines.append("- score reasons:")
                for reason in f.score_reasons:
                    lines.append(f"    - {reason}")
            lines.append("")
    lines.append("")

    # 4. Local diagnosis summary by label
    lines.append("## Local diagnosis summary by label")
    lines.append("")
    if report.by_label:
        for label_id, count in sorted(report.by_label.items(), key=lambda x: (-x[1], x[0])):
            title = get_label(label_id).title
            lines.append(f"- {label_id} ({count}): {title}")
    else:
        lines.append("_No labels._")
    lines.append("")

    # 5. Recommended actions
    lines.append("## Recommended actions")
    lines.append("")
    if report.recommended_actions:
        for action in report.recommended_actions:
            lines.append(f"- {action}")
    else:
        lines.append("_None._")
    lines.append("")

    # 6. Optional raw evidence references
    if report.evidence_refs:
        lines.append("## Raw evidence references")
        lines.append("")
        for ref in report.evidence_refs:
            lines.append(f"- {ref}")
        lines.append("")
        lines.append(
            "The `.opt.yaml` files remain the source of truth; local labels and "
            "scores express developer relevance, not absolute truth."
        )

    return "\n".join(lines).rstrip("\n") + "\n"
