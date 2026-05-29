"""Template-based local explanations (offline, evidence-first).

Given normalized records, classify + rank them and render concise,
deterministic explanations from the label taxonomy templates. No network, no
LLM, no Ollama.
"""

from __future__ import annotations

from explncc.local.ranker import LocalRankerV1, RankedFinding
from explncc.local.taxonomy import get_label
from explncc.models import OptimizationRecord


def _loc(record: OptimizationRecord) -> str:
    parts: list[str] = []
    if record.file:
        parts.append(record.file)
    if record.line is not None:
        parts.append(str(record.line))
    return ":".join(parts) if parts else "unknown location"


def explain_finding(finding: RankedFinding) -> str:
    """Render an evidence-first explanation for one ranked finding."""

    record = finding.record
    label = get_label(finding.label)
    lines: list[str] = []

    lines.append("Compiler evidence:")
    if record is not None:
        lines.append(f"- pass: {record.pass_name or '?'}")
        lines.append(f"- kind: {record.kind or '?'}")
        if record.function:
            lines.append(f"- function: {record.function}")
        loc = _loc(record)
        if loc != "unknown location":
            lines.append(f"- location: {loc}")
        if record.message:
            lines.append(f"- message: {record.message.strip()}")
    else:
        lines.append("- (no record attached)")
    lines.append("")

    lines.append("Local diagnosis:")
    lines.append(f"- label: {finding.label}")
    lines.append(f"- confidence: {finding.confidence}")
    lines.append(f"- severity: {finding.severity}")
    lines.append("")

    lines.append("Explanation:")
    lines.append(label.explanation_template)
    lines.append("")

    actions = finding.recommended_actions or label.recommended_actions
    if actions:
        lines.append("Recommended next steps:")
        for i, action in enumerate(actions, start=1):
            lines.append(f"{i}. {action}")

    return "\n".join(lines).rstrip("\n")


def build_local_explanation(
    records: list[OptimizationRecord],
    *,
    limit: int = 0,
    include_passed: bool = False,
    focus: str | None = None,
) -> str:
    """Classify + rank records and render template explanations for the top items.

    ``limit`` caps the number of findings explained (0 = all). The output is
    deterministic and entirely offline.
    """

    ranker = LocalRankerV1(include_passed=include_passed, focus=focus)
    findings = ranker.rank_records(records)
    if limit > 0:
        findings = findings[:limit]
    if not findings:
        return "No remarks to explain."
    blocks = [explain_finding(f) for f in findings]
    return "\n\n---\n\n".join(blocks)
