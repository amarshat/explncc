"""Fuse raw optimization records into per-decision findings.

A single compiler decision usually lands in ``.opt.yaml`` as several records.
A missed vectorization is a ``!Missed`` rollup ("loop not vectorized") plus a
sibling ``!Analysis`` record carrying the actual cause ("Backward loop carried
data dependence"). SLP emits near-identical records per instruction bundle at
the same location. Reading record-by-record therefore either punts on the cause
or repeats itself; this module groups the records back into one finding per
decision, with the compiler's own cause and suggestion attached.

Everything here is deterministic and offline. The compiler message text is
quoted, not paraphrased; the only synthesis is the short headline label.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from explncc.demangle import demangle_names
from explncc.models import OptimizationRecord

# Passes whose remarks are per-instruction or bookkeeping noise for triage.
NOISE_PASSES = frozenset({"asm-printer", "prologepilog", "size-info", "annotation"})

# How far (in lines) a cause analysis may sit from its missed rollup.
_CAUSE_LINE_SLACK = 3

_SEVERITY = {
    "vectorize-missed": 70,
    "hls-missed": 65,
    "inline-missed": 55,
    "slp-missed": 45,
    "other-missed": 35,
    "spills": 25,
    "analysis": 20,
    "passed": 10,
}

_INTERLEAVE_RE = re.compile(r"interleaved count: (\d+)")
_LEADING_INT_RE = re.compile(r"^(\d+)\b")


class FusedFinding(BaseModel):
    """One compiler decision: primary record plus its cause records."""

    category: str
    severity: int
    headline: str
    kind: str | None = None
    pass_name: str | None = None
    remark_name: str | None = None
    function: str | None = None
    function_display: str | None = None
    file: str | None = None
    line: int | None = None
    column: int | None = None
    caret_column: int | None = Field(
        default=None,
        description="Column of the cause record (points at the offending expression).",
    )
    cause: str | None = Field(
        default=None,
        description="The compiler's own analysis message for this decision, cleaned.",
    )
    suggestion: str | None = Field(
        default=None,
        description="Compiler-suggested action extracted verbatim from the remark message.",
    )
    count: int = Field(default=1, description="Raw records folded into this finding.")
    records: list[OptimizationRecord] = Field(default_factory=list)

    def location(self) -> str:
        parts: list[str] = []
        if self.file:
            parts.append(self.file)
        if self.line is not None:
            parts.append(str(self.line))
        return ":".join(parts) if parts else "unknown location"

    def finding_key(self) -> str:
        return (
            f"{self.pass_name or '?'}:{self.kind or '?'}:{self.remark_name or '?'}:"
            f"{self.function or '?'}:{self.file or '?'}:{self.line if self.line is not None else '?'}"
        )


def _is_noise(record: OptimizationRecord) -> bool:
    return (record.pass_name or "") in NOISE_PASSES


def _dedup_key(record: OptimizationRecord) -> tuple[object, ...]:
    return (
        record.kind,
        record.pass_name,
        record.remark_name,
        record.function,
        record.file,
        record.line,
        record.column,
        record.message,
    )


def _split_suggestion(message: str) -> tuple[str, str | None]:
    """Pull the compiler's ``Use ...`` sentence out of a remark message."""

    suggestion: str | None = None
    kept_segments: list[str] = []
    for segment in message.split("\n"):
        match = re.search(r"Use .+$", segment)
        if match and suggestion is None:
            suggestion = match.group(0).strip().rstrip(".")
            remainder = segment[: match.start()].strip()
            if remainder:
                kept_segments.append(remainder)
        else:
            stripped = segment.strip()
            if stripped:
                kept_segments.append(stripped)
    cleaned = " ".join(kept_segments)
    return cleaned, suggestion


def _clean_cause(message: str) -> tuple[str, str | None]:
    text = message
    prefix = "loop not vectorized: "
    if text.startswith(prefix):
        text = text[len(prefix) :]
    cleaned, suggestion = _split_suggestion(text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    return cleaned, suggestion


def _vectorize_cause_label(cause_records: list[OptimizationRecord]) -> str | None:
    blob = " ".join(f"{r.remark_name or ''} {(r.message or '')}" for r in cause_records).lower()
    if not blob.strip():
        return None
    if "loop carried" in blob or "unsafe dependent" in blob or "unsafedep" in blob:
        return "loop-carried dependence"
    if "reorder memory operations" in blob or "alias" in blob or "memory independence" in blob:
        return "possible pointer aliasing"
    if "reorder floating-point" in blob or "cantreorderfpops" in blob:
        return "floating-point reduction order"
    if "libcall" in blob or "call instruction" in blob or "cannot be vectorized because" in blob:
        return "non-vectorizable call"
    if "control flow" in blob:
        return "complex control flow"
    return None


def _display(name: str | None, name_map: dict[str, str]) -> str | None:
    if name is None:
        return None
    return name_map.get(name, name)


def _headline_and_category(
    record: OptimizationRecord,
    cause_records: list[OptimizationRecord],
    name_map: dict[str, str],
) -> tuple[str, str]:
    p = record.pass_name or ""
    name = record.remark_name or ""
    kind = record.kind or ""
    message = record.message or ""

    if p == "loop-vectorize" and kind == "missed":
        label = _vectorize_cause_label(cause_records)
        return (f"not vectorized: {label}" if label else "not vectorized"), "vectorize-missed"
    if p == "loop-vectorize" and kind == "passed" and name == "Vectorized":
        vf = record.vectorization_factor
        match = _INTERLEAVE_RE.search(message)
        ic = match.group(1) if match else None
        bits = []
        if vf is not None:
            bits.append(f"width {vf}")
        if ic is not None:
            bits.append(f"interleave {ic}")
        detail = f" ({', '.join(bits)})" if bits else ""
        return f"vectorized{detail}", "passed"
    if p == "slp-vectorizer" and kind == "missed":
        if record.cost is not None and record.threshold is not None:
            return (
                f"SLP not beneficial (cost {record.cost} >= threshold {record.threshold})",
                "slp-missed",
            )
        return f"SLP missed ({name})", "slp-missed"
    if p == "inline" and kind == "missed":
        callee = _display(record.callee, name_map)
        if name == "NoDefinition":
            who = callee or "the callee"
            return f"not inlined: {who} has no definition in this TU", "inline-missed"
        if record.cost is not None and record.threshold is not None:
            return (
                f"not inlined: cost {record.cost} > threshold {record.threshold}",
                "inline-missed",
            )
        return f"not inlined ({name})", "inline-missed"
    if p == "inline" and kind == "passed":
        caller = _display(record.caller, name_map)
        target = f" into {caller}" if caller else ""
        return f"inlined{target}", "passed"
    if p == "regalloc" and name == "SpillReloadCopies":
        match = _LEADING_INT_RE.search(message)
        n = match.group(1) if match else None
        detail = f" ({n} virtual registers)" if n else ""
        return f"register spill/reload copies{detail}", "spills"
    if "loop-unroll" in p and name == "FullyUnrolled":
        u = record.unroll_factor
        detail = f" ({u} iterations)" if u else ""
        return f"fully unrolled{detail}", "passed"
    if p.startswith("hls"):
        if name == "IINotAchieved":
            ii, tgt = record.initiation_interval, record.target_ii
            if ii is not None and tgt is not None:
                return f"II target missed (achieved {ii} vs target {tgt})", "hls-missed"
            return "II target missed", "hls-missed"
        if name == "LoopNotPipelined":
            return "not pipelined", "hls-missed"
        if name == "Pipelined":
            ii = record.initiation_interval
            detail = f" (II={ii})" if ii is not None else ""
            return f"pipelined{detail}", "passed"
    if name == "LoadClobbered":
        return "load not eliminated (may be clobbered)", "other-missed"
    if kind == "missed":
        return f"missed: {p or '?'}/{name or '?'}", "other-missed"
    if kind == "analysis":
        return f"analysis: {p or '?'}/{name or '?'}", "analysis"
    return f"{kind or '?'}: {p or '?'}/{name or '?'}", "passed" if kind == "passed" else "analysis"


def _build_finding(
    primary: OptimizationRecord,
    cause_records: list[OptimizationRecord],
    extra_count: int,
    name_map: dict[str, str],
) -> FusedFinding:
    headline, category = _headline_and_category(primary, cause_records, name_map)
    cause: str | None = None
    suggestion: str | None = None
    caret_column = primary.column
    if cause_records:
        cleaned_parts: list[str] = []
        for c in cause_records:
            if not c.message:
                continue
            cleaned, sug = _clean_cause(c.message)
            if cleaned:
                cleaned_parts.append(cleaned)
            if sug and suggestion is None:
                suggestion = sug
        if cleaned_parts:
            cause = "; ".join(dict.fromkeys(cleaned_parts))
        first_with_col = next((c for c in cause_records if c.column is not None), None)
        if first_with_col is not None:
            caret_column = first_with_col.column
    elif primary.message and primary.kind == "missed":
        cleaned, sug = _clean_cause(primary.message)
        if sug:
            suggestion = sug
        # Keep the primary message as cause only when it says more than the headline.
        if cleaned and cleaned.lower() not in {"loop not vectorized", ""}:
            cause = cleaned

    return FusedFinding(
        category=category,
        severity=_SEVERITY[category],
        headline=headline,
        kind=primary.kind,
        pass_name=primary.pass_name,
        remark_name=primary.remark_name,
        function=primary.function,
        function_display=_display(primary.function, name_map),
        file=primary.file,
        line=primary.line,
        column=primary.column,
        caret_column=caret_column,
        cause=cause,
        suggestion=suggestion,
        count=1 + len(cause_records) + extra_count,
        records=[primary, *cause_records],
    )


def fuse_records(
    records: list[OptimizationRecord],
    *,
    include_noise: bool = False,
    name_map: dict[str, str] | None = None,
) -> list[FusedFinding]:
    """Group raw records into findings: one per compiler decision.

    ``name_map`` overrides demangling (tests inject a fixed map); when ``None``
    the local demangler is used and silently degrades to mangled names.
    """

    kept: list[OptimizationRecord] = []
    dup_counts: dict[tuple[object, ...], int] = {}
    for record in records:
        if not include_noise and _is_noise(record):
            continue
        key = _dedup_key(record)
        if key in dup_counts:
            dup_counts[key] += 1
            continue
        dup_counts[key] = 1
        kept.append(record)

    if name_map is None:
        names = [r.function for r in kept if r.function]
        names += [r.callee for r in kept if r.callee]
        names += [r.caller for r in kept if r.caller]
        name_map = demangle_names(names)

    missed = [r for r in kept if r.kind == "missed"]
    analyses = [r for r in kept if r.kind == "analysis"]
    passed = [r for r in kept if r.kind == "passed"]

    consumed: set[int] = set()
    findings: list[FusedFinding] = []

    for primary in missed:
        causes: list[OptimizationRecord] = []
        for idx, candidate in enumerate(analyses):
            if idx in consumed:
                continue
            if candidate.pass_name != primary.pass_name:
                continue
            if candidate.function != primary.function or candidate.file != primary.file:
                continue
            if (
                candidate.line is not None
                and primary.line is not None
                and abs(candidate.line - primary.line) > _CAUSE_LINE_SLACK
            ):
                continue
            causes.append(candidate)
            consumed.add(idx)
        extra = dup_counts[_dedup_key(primary)] - 1
        findings.append(_build_finding(primary, causes, extra, name_map))

    for idx, record in enumerate(analyses):
        if idx in consumed:
            continue
        extra = dup_counts[_dedup_key(record)] - 1
        findings.append(_build_finding(record, [], extra, name_map))

    for record in passed:
        extra = dup_counts[_dedup_key(record)] - 1
        findings.append(_build_finding(record, [], extra, name_map))

    findings.sort(
        key=lambda f: (
            -f.severity,
            f.file or "",
            f.line if f.line is not None else 1 << 30,
            f.pass_name or "",
            f.remark_name or "",
            f.function or "",
        ),
    )
    return findings
