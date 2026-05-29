"""Deterministic renderers for local classify / rank output.

Formats: table (rows for rich), json, jsonl, markdown. All output is
network-free and screenshot-friendly.
"""

from __future__ import annotations

import json

from explncc.local.classifier import ClassifyFocus, classify_record
from explncc.local.contracts import ClassificationResult
from explncc.local.ranker import RankedFinding
from explncc.models import OptimizationRecord

CLASSIFY_FORMATS = ("table", "json", "jsonl", "markdown")
RANK_FORMATS = ("table", "json", "jsonl", "markdown")


def _loc(record: OptimizationRecord) -> str:
    parts: list[str] = []
    if record.file:
        parts.append(record.file)
    if record.line is not None:
        parts.append(str(record.line))
    return ":".join(parts) if parts else ""


def _truncate(text: str | None, limit: int) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "\u2026"


# --- classify -------------------------------------------------------------

CLASSIFY_COLUMNS = (
    "function",
    "location",
    "pass",
    "kind",
    "label",
    "confidence",
    "reason",
    "recommended action",
)


def classification_rows(
    records: list[OptimizationRecord],
    results: list[ClassificationResult],
) -> list[list[str]]:
    rows: list[list[str]] = []
    for record, res in zip(records, results, strict=True):
        reason = res.evidence_reasons[0] if res.evidence_reasons else ""
        action = res.recommended_actions[0] if res.recommended_actions else ""
        rows.append(
            [
                record.function or "",
                _loc(record),
                record.pass_name or "",
                record.kind or "",
                res.label,
                res.confidence,
                _truncate(reason, 60),
                _truncate(action, 60),
            ]
        )
    return rows


def _classification_to_dict(
    record: OptimizationRecord,
    res: ClassificationResult,
) -> dict[str, object]:
    return {
        "function": record.function,
        "file": record.file,
        "line": record.line,
        "pass": record.pass_name,
        "kind": record.kind,
        "remark_name": record.remark_name,
        "message": record.message,
        "label": res.label,
        "confidence": res.confidence,
        "score_hint": res.score_hint,
        "evidence_reasons": res.evidence_reasons,
        "missing_context": res.missing_context,
        "recommended_actions": res.recommended_actions,
    }


def render_classifications(
    records: list[OptimizationRecord],
    results: list[ClassificationResult],
    fmt: str,
) -> str:
    fmt = fmt.strip().lower()
    if fmt == "json":
        payload = [_classification_to_dict(r, c) for r, c in zip(records, results, strict=True)]
        return json.dumps(payload, indent=2, ensure_ascii=False)
    if fmt == "jsonl":
        lines = [
            json.dumps(_classification_to_dict(r, c), ensure_ascii=False)
            for r, c in zip(records, results, strict=True)
        ]
        return "\n".join(lines)
    if fmt == "markdown":
        return _classifications_markdown(records, results)
    raise ValueError(f"unknown classify format: {fmt!r}")


def _classifications_markdown(
    records: list[OptimizationRecord],
    results: list[ClassificationResult],
) -> str:
    lines = ["# Local Classification", ""]
    lines.append("| function | location | pass | kind | label | confidence | reason |")
    lines.append("|---|---|---|---|---|---|---|")
    for record, res in zip(records, results, strict=True):
        reason = _truncate(res.evidence_reasons[0] if res.evidence_reasons else "", 80)
        lines.append(
            f"| {record.function or ''} | {_loc(record)} | {record.pass_name or ''} | "
            f"{record.kind or ''} | {res.label} | {res.confidence} | {reason} |"
        )
    return "\n".join(lines)


def classify(
    records: list[OptimizationRecord],
    *,
    focus: ClassifyFocus = None,
) -> list[ClassificationResult]:
    return [classify_record(r, focus=focus) for r in records]


# --- rank ------------------------------------------------------------------

RANK_COLUMNS = (
    "rank",
    "score",
    "severity",
    "label",
    "confidence",
    "function",
    "location",
    "pass",
    "kind",
)


def ranked_rows(findings: list[RankedFinding]) -> list[list[str]]:
    rows: list[list[str]] = []
    for f in findings:
        record = f.record
        rows.append(
            [
                str(f.rank),
                f"{f.score:g}",
                f.severity,
                f.label,
                f.confidence,
                (record.function if record and record.function else ""),
                (_loc(record) if record else ""),
                (record.pass_name if record and record.pass_name else ""),
                (record.kind if record and record.kind else ""),
            ]
        )
    return rows


def render_findings(findings: list[RankedFinding], fmt: str) -> str:
    fmt = fmt.strip().lower()
    if fmt == "json":
        return json.dumps([f.to_dict() for f in findings], indent=2, ensure_ascii=False)
    if fmt == "jsonl":
        return "\n".join(json.dumps(f.to_dict(), ensure_ascii=False) for f in findings)
    if fmt == "markdown":
        return _findings_markdown(findings)
    raise ValueError(f"unknown rank format: {fmt!r}")


def _findings_markdown(findings: list[RankedFinding]) -> str:
    lines = ["# Ranked Compiler Optimization Findings", ""]
    if not findings:
        lines.append("_No findings._")
        return "\n".join(lines)
    for f in findings:
        record = f.record
        lines.append(f"## {f.rank}. {f.label} (score {f.score:g}, {f.severity})")
        lines.append("")
        lines.append(f"- **confidence:** {f.confidence}")
        if record is not None:
            lines.append("- **compiler evidence:**")
            lines.append(f"    - pass: {record.pass_name or '?'}")
            lines.append(f"    - kind: {record.kind or '?'}")
            if record.function:
                lines.append(f"    - function: {record.function}")
            loc = _loc(record)
            if loc:
                lines.append(f"    - location: {loc}")
            if record.message:
                lines.append(f"    - message: {_truncate(record.message, 200)}")
        if f.score_reasons:
            lines.append("- **score reasons:**")
            for reason in f.score_reasons:
                lines.append(f"    - {reason}")
        if f.recommended_actions:
            lines.append("- **recommended actions:**")
            for action in f.recommended_actions:
                lines.append(f"    - {action}")
        lines.append("")
    return "\n".join(lines).rstrip("\n")
