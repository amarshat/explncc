"""Semantic compiler optimization diffs for CI (report-diff)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from explncc.diffing import diff_records
from explncc.exporters import record_to_json_dict
from explncc.models import OptimizationRecord
from explncc.report_types import REPORT_SCHEMA_VERSION

ChangeClass = Literal["regression", "improvement", "neutral_change", "unknown"]


@dataclass
class SemanticChange:
    classification: ChangeClass
    change_type: str
    description: str
    record_hash: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


@dataclass
class ReportDiffResult:
    schema_version: str
    before_label: str
    after_label: str
    changes: list[SemanticChange] = field(default_factory=list)
    policy_before: str | None = None
    policy_after: str | None = None
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "before_label": self.before_label,
            "after_label": self.after_label,
            "changes": [asdict(c) for c in self.changes],
            "policy_before": self.policy_before,
            "policy_after": self.policy_after,
            "summary": self.summary,
        }


def _record_hash(record: OptimizationRecord) -> str:
    payload = record.fingerprint()
    return json.dumps(payload, sort_keys=True, default=str)


def _loc_key(record: OptimizationRecord) -> tuple[Any, ...]:
    return (
        record.pass_name,
        record.remark_name,
        record.function,
        record.file,
        record.line,
        record.column,
    )


def _classify_change(change_type: str) -> ChangeClass:
    if change_type in {
        "new_missed",
        "vectorization_lost",
        "missed_count_increased",
        "kind_regression",
    }:
        return "regression"
    if change_type in {
        "resolved_missed",
        "vectorization_gained",
        "missed_count_decreased",
        "kind_improvement",
    }:
        return "improvement"
    if change_type in {"message_changed", "cost_changed", "vectorization_factor_changed"}:
        return "neutral_change"
    return "unknown"


def build_report_diff(
    before: list[OptimizationRecord],
    after: list[OptimizationRecord],
    *,
    before_label: str = "before",
    after_label: str = "after",
    only_regressions: bool = False,
    include_improvements: bool = True,
) -> ReportDiffResult:
    base = diff_records(before, after)
    changes: list[SemanticChange] = []

    for r in base.new_missed:
        changes.append(
            SemanticChange(
                classification="regression",
                change_type="new_missed",
                description=f"New missed remark: {r.pass_name}/{r.remark_name}",
                record_hash=_record_hash(r),
                after=record_to_json_dict(r),
            ),
        )

    for r in base.resolved_missed:
        changes.append(
            SemanticChange(
                classification="improvement",
                change_type="resolved_missed",
                description=f"Resolved missed remark: {r.pass_name}/{r.remark_name}",
                record_hash=_record_hash(r),
                before=record_to_json_dict(r),
            ),
        )

    before_by_loc = {_loc_key(r): r for r in before}
    after_by_loc = {_loc_key(r): r for r in after}
    for key in set(before_by_loc) & set(after_by_loc):
        b, a = before_by_loc[key], after_by_loc[key]
        if b.kind != a.kind:
            changes.append(
                SemanticChange(
                    classification=_classify_change("kind_regression" if a.kind == "missed" else "kind_improvement"),
                    change_type="kind_changed",
                    description=f"Kind changed {b.kind} → {a.kind} for {a.pass_name}/{a.remark_name}",
                    record_hash=_record_hash(a),
                    before=record_to_json_dict(b),
                    after=record_to_json_dict(a),
                ),
            )
        if b.vectorization_factor != a.vectorization_factor:
            ct = "vectorization_factor_changed"
            if b.vectorization_factor and not a.vectorization_factor:
                ct = "vectorization_lost"
            elif a.vectorization_factor and not b.vectorization_factor:
                ct = "vectorization_gained"
            changes.append(
                SemanticChange(
                    classification=_classify_change(ct),
                    change_type=ct,
                    description=(
                        f"Vectorization factor {b.vectorization_factor} → {a.vectorization_factor} "
                        f"for {a.pass_name}/{a.remark_name}"
                    ),
                    record_hash=_record_hash(a),
                    before=record_to_json_dict(b),
                    after=record_to_json_dict(a),
                ),
            )
        if b.message != a.message:
            changes.append(
                SemanticChange(
                    classification="neutral_change",
                    change_type="message_changed",
                    description=f"Message changed for {a.pass_name}/{a.remark_name}",
                    record_hash=_record_hash(a),
                    before=record_to_json_dict(b),
                    after=record_to_json_dict(a),
                ),
            )
        if b.cost != a.cost:
            changes.append(
                SemanticChange(
                    classification="neutral_change",
                    change_type="cost_changed",
                    description=f"Cost changed for {a.pass_name}/{a.remark_name}",
                    record_hash=_record_hash(a),
                    before=record_to_json_dict(b),
                    after=record_to_json_dict(a),
                ),
            )

    if only_regressions:
        changes = [c for c in changes if c.classification == "regression"]
    elif not include_improvements:
        changes = [c for c in changes if c.classification != "improvement"]

    summary = {
        "new_missed": len(base.new_missed),
        "resolved_missed": len(base.resolved_missed),
        "pass_count_delta": base.pass_count_delta,
        "reason_delta_missed": base.reason_delta_missed,
        "function_delta_missed": base.function_delta_missed,
        "total_changes": len(changes),
    }
    return ReportDiffResult(
        schema_version=REPORT_SCHEMA_VERSION,
        before_label=before_label,
        after_label=after_label,
        changes=changes,
        summary=summary,
    )


def render_report_diff_markdown(result: ReportDiffResult, *, top_changes: int = 15) -> str:
    lines = [
        f"# Compiler optimization diff: {result.before_label} → {result.after_label}",
        "",
        "## Summary",
        "",
    ]
    for k, v in result.summary.items():
        lines.append(f"- **{k}:** {v}")
    lines.append("")
    lines.append("## Changes")
    lines.append("")
    shown = result.changes[:top_changes] if top_changes > 0 else result.changes
    if not shown:
        lines.append("_No classified changes in this slice._")
    else:
        for i, c in enumerate(shown, start=1):
            lines.append(f"### {i}. [{c.classification}] {c.change_type}")
            lines.append("")
            lines.append(c.description)
            lines.append("")
    lines.append("_Observed compiler evidence only; source edits are not inferred._")
    return "\n".join(lines)


def render_report_diff_github(result: ReportDiffResult, *, top_changes: int = 15) -> str:
    lines = [
        "## Compiler optimization diff",
        "",
        f"**{result.before_label} → {result.after_label}**",
        "",
        f"- New missed: {result.summary.get('new_missed', 0)}",
        f"- Resolved missed: {result.summary.get('resolved_missed', 0)}",
        "",
        "<details>",
        "<summary>Semantic changes</summary>",
        "",
    ]
    shown = result.changes[:top_changes] if top_changes > 0 else result.changes
    if not shown:
        lines.append("_No changes._")
    else:
        lines.append("| Class | Type | Description |")
        lines.append("| --- | --- | --- |")
        for c in shown:
            lines.append(f"| {c.classification} | {c.change_type} | {c.description} |")
    lines.append("")
    lines.append("</details>")
    lines.append("")
    lines.append("_Raw `.opt.yaml` files remain authoritative._")
    return "\n".join(lines)


def render_report_diff(fmt: str, result: ReportDiffResult, *, top_changes: int = 15) -> str:
    if fmt == "json":
        return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)
    if fmt == "github":
        return render_report_diff_github(result, top_changes=top_changes)
    return render_report_diff_markdown(result, top_changes=top_changes)
