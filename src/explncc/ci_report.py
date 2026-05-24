"""CI-oriented reports: Markdown, JSON, HTML, and GitHub-flavored snippets."""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from typing import Any

from explncc import __version__
from explncc.checks import PolicyResult
from explncc.evidence import _target_fields
from explncc.exporters import record_to_json_dict
from explncc.models import OptimizationRecord
from explncc.report_types import (
    REPORT_SCHEMA_VERSION,
    ExplanationInfo,
    ReportBuildOptions,
    ReportMetadata,
    ReportSourceInfo,
)
from explncc.stats import aggregate

ReportFormat = str


def parse_report_format(value: str) -> str:
    v = value.strip().lower()
    if v in {"markdown", "json", "github", "html"}:
        return v
    msg = f"unknown report format: {value!r}"
    raise ValueError(msg)


def _normalize_whitespace(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _location_string(record: OptimizationRecord) -> str:
    if not record.file:
        return "—"
    loc = record.file
    if record.line is not None:
        loc += f":{record.line}"
        if record.column is not None:
            loc += f":{record.column}"
    return loc


def _compiler_identity(records: list[OptimizationRecord]) -> str | None:
    for r in records:
        meta = r.tool_version_metadata
        if not meta:
            continue
        for key in ("ClangVersion", "LLVMVersion", "Producer", "Version"):
            val = meta.get(key)
            if val:
                return str(val)
    return None


def _target_triple(records: list[OptimizationRecord]) -> str | None:
    for r in records:
        triple, _, _ = _target_fields(r.tool_version_metadata)
        if triple:
            return triple
    return None


def top_missed_remarks(records: list[OptimizationRecord], limit: int) -> list[OptimizationRecord]:
    missed = [r for r in records if r.kind == "missed"]
    return missed[:limit] if limit > 0 else missed


def top_analysis_remarks(records: list[OptimizationRecord], limit: int) -> list[OptimizationRecord]:
    analysis = [r for r in records if r.kind == "analysis"]
    return analysis[:limit] if limit > 0 else analysis


def top_passed_remarks(records: list[OptimizationRecord], limit: int) -> list[OptimizationRecord]:
    passed = [r for r in records if r.kind == "passed"]
    return passed[:limit] if limit > 0 else passed


def _compact_remark(record: OptimizationRecord) -> dict[str, Any]:
    return {
        "kind": record.kind,
        "pass": record.pass_name,
        "remark": record.remark_name,
        "function": record.function,
        "location": _location_string(record),
        "message": record.message,
        "vectorization_factor": record.vectorization_factor,
        "interleave_count": None,
        "scalar_cost": record.cost if record.cost and "vector" not in (record.pass_name or "").lower() else None,
        "vector_cost": record.cost if record.cost and "vector" in (record.pass_name or "").lower() else None,
        "record": record_to_json_dict(record),
    }


def _missed_remarks_markdown_sections(
    missed: list[OptimizationRecord],
    *,
    message_max_chars: int = 4000,
) -> list[str]:
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


def _explain_label(backend: str | None) -> str | None:
    if not backend:
        return None
    b = backend.lower()
    if b == "rule":
        return "Rule-based interpretation"
    return "AI-assisted interpretation"


def build_json_payload(
    records: list[OptimizationRecord],
    *,
    source: ReportSourceInfo,
    metadata: ReportMetadata,
    options: ReportBuildOptions,
    policy: PolicyResult | None,
    explanation: ExplanationInfo,
    generated_at: str | None = None,
) -> dict[str, Any]:
    stats = aggregate(records)
    missed = top_missed_remarks(records, options.top_missed)
    analysis = top_analysis_remarks(records, options.top_analysis)
    passed = top_passed_remarks(records, options.top_passed) if options.include_passed else []

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": generated_at or datetime.now(tz=UTC).isoformat(),
        "explncc_version": __version__,
        "title": options.title,
        "compiler_identity": _compiler_identity(records),
        "target_triple": _target_triple(records),
        "source": source.to_dict(),
        "summary": {
            "total": stats["total"],
            "by_kind": stats.get("by_kind", {}),
            "by_pass": stats.get("by_pass", {}),
            "by_function": stats.get("by_function", {}),
            "by_reason": stats.get("by_reason", {}),
        },
        "top_missed": [_compact_remark(r) for r in missed],
        "top_analysis": [_compact_remark(r) for r in analysis],
        "top_passed": [_compact_remark(r) for r in passed] if options.include_passed else None,
        "policy": policy.to_dict() if policy is not None else None,
        "explanations": explanation.to_dict(),
        "metadata": metadata.to_dict(),
    }


def _build_metadata_section(
    source: ReportSourceInfo,
    metadata: ReportMetadata,
    *,
    generated_at: str,
    target_triple: str | None,
    explain_status: str,
) -> list[str]:
    lines = [
        "## Build Metadata",
        "",
        f"- **Input path:** `{source.input_path}`",
        f"- **Generated:** {generated_at}",
        f"- **Remark files:** {source.file_count}",
        f"- **Remarks loaded:** {source.remark_count}",
    ]
    if metadata.git_sha:
        lines.append(f"- **Git SHA:** `{metadata.git_sha}`")
    if metadata.branch:
        lines.append(f"- **Branch:** `{metadata.branch}`")
    if metadata.pr_number:
        lines.append(f"- **PR:** `{metadata.pr_number}`")
    if metadata.build_id:
        lines.append(f"- **Build ID:** `{metadata.build_id}`")
    if metadata.ci_provider:
        lines.append(f"- **CI provider:** `{metadata.ci_provider}`")
    if target_triple:
        lines.append(f"- **Target:** `{target_triple}`")
    lines.append(f"- **Explanation:** {explain_status}")
    lines.append("")
    return lines


def build_markdown_report(
    records: list[OptimizationRecord],
    *,
    source: ReportSourceInfo,
    metadata: ReportMetadata,
    options: ReportBuildOptions,
    policy: PolicyResult | None,
    explanation: ExplanationInfo,
    generated_at: str | None = None,
) -> str:
    stats = aggregate(records)
    ts = generated_at or datetime.now(tz=UTC).isoformat()
    explain_status = "disabled" if not explanation.enabled else (explanation.backend or "enabled")
    lines: list[str] = [f"# {options.title}", ""]
    lines.extend(
        _build_metadata_section(
            source,
            metadata,
            generated_at=ts,
            target_triple=_target_triple(records),
            explain_status=explain_status,
        ),
    )

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total remarks:** {stats['total']}")
    if stats.get("by_kind"):
        kinds = ", ".join(f"{k}: {v}" for k, v in list(stats["by_kind"].items())[:8])
        lines.append(f"- **By kind:** {kinds}")
    if stats.get("by_pass"):
        passes = ", ".join(f"{k}: {v}" for k, v in list(stats["by_pass"].items())[:8])
        lines.append(f"- **Top passes:** {passes}")
    lines.append("")

    lines.append("## Policy")
    lines.append("")
    if policy is None:
        lines.append("_No deterministic policy thresholds configured._")
    elif policy.ok:
        lines.append("**Status:** pass")
    else:
        lines.append("**Status:** fail")
        for t in policy.thresholds:
            if not t.ok:
                lines.append(f"- `{t.name}`: actual {t.actual} > limit {t.limit}")
    lines.append("")

    lines.append("## Top Missed Optimizations")
    lines.append("")
    missed = top_missed_remarks(records, options.top_missed)
    if not missed:
        lines.append("_No missed remarks in this slice._")
    else:
        lines.extend(_missed_remarks_markdown_sections(missed, message_max_chars=options.message_max_chars))
    lines.append("")

    if explanation.enabled and explanation.items:
        label = explanation.label or "Optional interpretation"
        lines.append(f"## {label}")
        lines.append("")
        if explanation.warning:
            lines.append(f"> **Warning:** {explanation.warning}")
            lines.append("")
        for item in explanation.items:
            lines.append(item.get("text", "").strip())
            lines.append("")
    elif policy is not None and not policy.ok and explanation.enabled:
        lines.append("## Optional triage notes")
        lines.append("")
        for item in explanation.items:
            lines.append(item.get("text", "").strip())
            lines.append("")

    lines.append("## Raw Artifact Notice")
    lines.append("")
    lines.append("The `.opt.yaml` file remains the source of truth. This report summarizes normalized compiler evidence.")
    lines.append("")
    return "\n".join(lines)


def build_github_comment(
    records: list[OptimizationRecord],
    *,
    source: ReportSourceInfo,
    metadata: ReportMetadata,
    options: ReportBuildOptions,
    policy: PolicyResult | None,
    explanation: ExplanationInfo,
) -> str:
    stats = aggregate(records)
    missed_inline = sum(
        1
        for r in records
        if r.kind == "missed" and r.pass_name and "inline" in r.pass_name.lower()
    )
    missed_vectorize = sum(
        1
        for r in records
        if r.kind == "missed" and r.pass_name and "vector" in r.pass_name.lower()
    )
    policy_status = "pass" if policy is None or policy.ok else "fail"
    lines: list[str] = [
        "## Compiler Optimization Report",
        "",
        f"**Policy:** {policy_status}",
        f"**Total remarks:** {stats['total']}",
        f"**Missed loop-vectorize / vector passes:** {missed_vectorize}",
        f"**Missed inline:** {missed_inline}",
    ]
    if metadata.git_sha:
        lines.append(f"**Git SHA:** `{metadata.git_sha[:12]}`")

    missed = top_missed_remarks(records, options.top_missed)
    if options.github_collapsible:
        lines.append("")
        lines.append("<details>")
        lines.append("<summary>Top missed optimizations</summary>")
        lines.append("")
        if not missed:
            lines.append("_None._")
        else:
            lines.append("| Pass | Remark | Function | Location |")
            lines.append("| --- | --- | --- | --- |")
            for r in missed:
                lines.append(
                    f"| `{r.pass_name or '—'}` | `{r.remark_name or '—'}` | "
                    f"`{r.function or '—'}` | `{_location_string(r)}` |",
                )
        lines.append("")
        lines.append("</details>")
    else:
        lines.append("")
        lines.extend(_missed_remarks_markdown_sections(missed))

    if explanation.enabled and explanation.items:
        label = explanation.label or "Optional interpretation"
        if options.github_collapsible:
            lines.append("<details>")
            lines.append(f"<summary>{label}</summary>")
            lines.append("")
        else:
            lines.append("")
            lines.append(f"### {label}")
            lines.append("")
        for item in explanation.items:
            lines.append(item.get("text", "").strip())
            lines.append("")
        if options.github_collapsible:
            lines.append("</details>")

    lines.append("")
    lines.append(
        "_Raw `.opt.yaml` and JSON report artifacts remain the source of truth; "
        "interpretation sections are assistive only._",
    )
    return "\n".join(lines)


def build_html_report(
    records: list[OptimizationRecord],
    *,
    source: ReportSourceInfo,
    metadata: ReportMetadata,
    options: ReportBuildOptions,
    policy: PolicyResult | None,
    explanation: ExplanationInfo,
) -> str:
    md = build_markdown_report(
        records,
        source=source,
        metadata=metadata,
        options=options,
        policy=policy,
        explanation=explanation,
    )
    esc = html.escape
    body = esc(md).replace("\n", "<br/>\n")
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'/>"
        f"<title>{esc(options.title)}</title></head><body><pre>{body}</pre></body></html>"
    )


def render_report(
    fmt: str,
    records: list[OptimizationRecord],
    *,
    source: ReportSourceInfo,
    metadata: ReportMetadata,
    options: ReportBuildOptions,
    policy: PolicyResult | None,
    explanation: ExplanationInfo,
) -> str:
    if fmt == "json":
        payload = build_json_payload(
            records,
            source=source,
            metadata=metadata,
            options=options,
            policy=policy,
            explanation=explanation,
        )
        return json.dumps(payload, indent=2, ensure_ascii=False)
    if fmt == "github":
        return build_github_comment(
            records,
            source=source,
            metadata=metadata,
            options=options,
            policy=policy,
            explanation=explanation,
        )
    if fmt == "html":
        return build_html_report(
            records,
            source=source,
            metadata=metadata,
            options=options,
            policy=policy,
            explanation=explanation,
        )
    return build_markdown_report(
        records,
        source=source,
        metadata=metadata,
        options=options,
        policy=policy,
        explanation=explanation,
    )
