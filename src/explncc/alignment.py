"""Heuristics for SIMD / vectorization / alignment-adjacent optimization remarks.

These are **documentary signals** for filtering and dataset construction, not ground
truth: Clang wording varies by version and target. Chapter 11 uses them to slice
``.opt.yaml`` for LLM training and evaluation workflows.
"""

from __future__ import annotations

from explncc.models import OptimizationRecord

# Pass names (substring match, lowercased) strongly tied to SIMD shaping.
_VECTOR_PASS_MARKERS: tuple[str, ...] = (
    "loop-vectorize",
    "slp-vectorizer",
    "interleaved",
)

# Message / remark-name substrings that often co-occur with alignment discussions.
_ALIGNMENT_MSG_MARKERS: tuple[str, ...] = (
    "align",
    "alignment",
    "misaligned",
    "scalarized",
    "vectorization",
    "vectorized",
    "simd",
    "interleave",
    "interleaved",
    "vector width",
    "runtime memory check",
    "uniform",
)

_REMARK_MARKERS: tuple[str, ...] = (
    "Vectorized",
    "NotBeneficial",
    "MissedDetails",
    "NotVectorized",
)


def alignment_signals(record: OptimizationRecord) -> list[str]:
    """Return human-readable tags explaining why a remark is included in the SIMD slice."""

    signals: list[str] = []
    pn = (record.pass_name or "").lower()
    msg = (record.message or "").lower()
    rn = record.remark_name or ""

    for m in _VECTOR_PASS_MARKERS:
        if m in pn:
            signals.append(f"pass:{m}")
    if record.vectorization_factor is not None:
        signals.append("field:vectorization_factor")
    for m in _ALIGNMENT_MSG_MARKERS:
        if m in msg:
            signals.append(f"msg:{m.replace(' ', '_')}")
    for m in _REMARK_MARKERS:
        if m in rn:
            signals.append(f"remark:{m}")

    return signals


def is_alignment_related(record: OptimizationRecord) -> bool:
    """True if any alignment/SIMD heuristic fired for this record."""

    return bool(alignment_signals(record))


def filter_alignment_related(records: list[OptimizationRecord]) -> list[OptimizationRecord]:
    """Keep only records that match :func:`is_alignment_related`."""

    return [r for r in records if is_alignment_related(r)]
