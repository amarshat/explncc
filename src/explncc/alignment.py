"""Heuristics for SIMD / vectorization / alignment-adjacent optimization remarks.

These are **documentary signals** for filtering and dataset construction, not ground
truth: Clang wording varies by version and target. Chapter 11 uses them to slice
``.opt.yaml`` for LLM training and evaluation workflows.

Evidence classification labels describe how strongly a remark supports an alignment
diagnosis — they are heuristics, not oracle labels.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

from explncc.models import OptimizationRecord

AlignmentLabel = Literal[
    "alignment_explicit",
    "alignment_plausible_not_proven",
    "alignment_unlikely_from_evidence",
    "insufficient_evidence",
    "not_alignment_related",
]

AlignmentConfidence = Literal["low", "medium", "high"]

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

# Direct alignment vocabulary — explicit evidence when present in remark text.
_EXPLICIT_ALIGNMENT_MARKERS: tuple[str, ...] = (
    "aligned load",
    "aligned store",
    "assume_aligned",
    "assumealigned",
    "aligned_alloc",
    "posix_memalign",
    "_mm_load_ps",
    "_mm256_load_ps",
    "_mm_loadu_ps",
    "_mm256_loadu_ps",
    "_mm_load_pd",
    "_mm256_load_pd",
    "_mm_loadu_pd",
    "_mm256_loadu_pd",
    "align metadata",
    "pointer alignment",
    "not aligned",
    "unaligned",
    "misaligned",
    "alignment",
    "aligned access",
)

# Remark patterns pointing to non-alignment root causes.
_ALIASING_MARKERS: tuple[str, ...] = (
    "aliasing",
    "alias",
    "independence",
    "memory independence",
    "cannot prove memory",
    "may alias",
    "pointer aliasing",
)

_COST_MARKERS: tuple[str, ...] = (
    "cost",
    "not beneficial",
    "threshold",
    "not profitable",
    "unprofitable",
    "beneficial to vectorize",
)

_OTHER_CAUSE_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("no definition", ("no definition", "undefined", "nod definition")),
    ("call in loop", ("call in loop", "function call in loop")),
    ("unsupported operation", ("unsupported operation", "unsupported")),
    ("reduction issue", ("reduction",)),
)

_DEFAULT_MISSING_CONTEXT: tuple[str, ...] = (
    "source_snippet",
    "ir_snippet",
    "assembly_snippet",
    "target_triple",
)


@dataclass(frozen=True)
class AlignmentClassification:
    """Heuristic alignment evidence classification for one normalized remark."""

    alignment_label: AlignmentLabel
    alignment_confidence: AlignmentConfidence
    evidence_reasons: list[str] = field(default_factory=list)
    missing_context: list[str] = field(default_factory=list)
    recommended_next_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


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


def _remark_text(record: OptimizationRecord) -> str:
    parts = [record.message or "", record.remark_name or "", record.reason or ""]
    return " ".join(parts).lower()


def _has_explicit_alignment_evidence(text: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    for marker in _EXPLICIT_ALIGNMENT_MARKERS:
        if marker in text:
            reasons.append(f"remark text mentions explicit alignment vocabulary: {marker!r}")
    # Standalone "align" (not already caught by "alignment") in compiler messages.
    if " align" in text or text.startswith("align"):
        if not any("alignment" in r for r in reasons):
            reasons.append("remark text mentions alignment-related wording")
    return bool(reasons), reasons


def _other_cause_reason(text: str) -> tuple[str | None, list[str]]:
    for marker in _ALIASING_MARKERS:
        if marker in text:
            return (
                "aliasing",
                ["remark points to memory independence / aliasing rather than alignment"],
            )
    for marker in _COST_MARKERS:
        if marker in text:
            return (
                "cost",
                ["remark points to vectorization cost / profitability rather than alignment"],
            )
    for label, markers in _OTHER_CAUSE_MARKERS:
        for marker in markers:
            if marker in text:
                return (
                    label,
                    [f"remark points to {label} rather than alignment"],
                )
    return None, []


def _is_simd_vectorization_involved(record: OptimizationRecord) -> bool:
    pn = (record.pass_name or "").lower()
    if any(m in pn for m in _VECTOR_PASS_MARKERS):
        return True
    if record.vectorization_factor is not None:
        return True
    text = _remark_text(record)
    return any(w in text for w in ("vectoriz", "simd", "interleave"))


def _default_missing_context() -> list[str]:
    return list(_DEFAULT_MISSING_CONTEXT)


def _next_steps_for_label(
    label: AlignmentLabel,
    cause: str | None = None,
) -> list[str]:
    if label == "alignment_explicit":
        return [
            "inspect allocation guarantees and pointer alignment assumptions",
            "check IR alignment metadata on relevant loads/stores",
            "compare assembly load/store forms (movaps vs movups, etc.)",
        ]
    if label == "alignment_plausible_not_proven":
        return [
            "inspect allocation guarantees and pointer arithmetic",
            "check IR alignment metadata before attributing a miss to alignment",
            "compare assembly load/store forms for alignment-sensitive mnemonics",
            "do not treat vectorization_factor alone as proof of misalignment",
        ]
    if label == "alignment_unlikely_from_evidence":
        if cause == "aliasing":
            return [
                "inspect aliasing contract",
                "check restrict/noalias assumptions",
                "do not attribute this miss to alignment without further evidence",
            ]
        if cause == "cost":
            return [
                "inspect scalar vs vector cost estimates in the remark",
                "review loop structure before attributing a miss to alignment",
                "do not attribute this miss to alignment without further evidence",
            ]
        return [
            "investigate the stated compiler reason before attributing to alignment",
            "do not attribute this miss to alignment without further evidence",
        ]
    if label == "insufficient_evidence":
        return [
            "attach source snippet around the debug location",
            "generate IR and assembly snippets for the function",
            "re-run classification after adding grounded compiler artifacts",
        ]
    return []


def classify_alignment(record: OptimizationRecord) -> AlignmentClassification:
    """Classify alignment evidence strength for a normalized remark (heuristic, not ground truth)."""

    signals = alignment_signals(record)
    text = _remark_text(record)
    missing = _default_missing_context()

    if not signals:
        return AlignmentClassification(
            alignment_label="not_alignment_related",
            alignment_confidence="high",
            evidence_reasons=[
                "remark does not match SIMD, vectorization, memory access, or alignment heuristics",
            ],
            missing_context=missing,
            recommended_next_steps=[],
        )

    explicit, explicit_reasons = _has_explicit_alignment_evidence(text)
    if explicit:
        return AlignmentClassification(
            alignment_label="alignment_explicit",
            alignment_confidence="high",
            evidence_reasons=explicit_reasons,
            missing_context=missing,
            recommended_next_steps=_next_steps_for_label("alignment_explicit"),
        )

    cause, cause_reasons = _other_cause_reason(text)
    if cause is not None:
        confidence: AlignmentConfidence = "high"
        return AlignmentClassification(
            alignment_label="alignment_unlikely_from_evidence",
            alignment_confidence=confidence,
            evidence_reasons=cause_reasons,
            missing_context=missing,
            recommended_next_steps=_next_steps_for_label(
                "alignment_unlikely_from_evidence",
                cause=cause,
            ),
        )

    if record.vectorization_factor is not None or (record.remark_name or "") == "Vectorized":
        return AlignmentClassification(
            alignment_label="alignment_plausible_not_proven",
            alignment_confidence="medium",
            evidence_reasons=[
                "successful vectorization is present but the remark does not explicitly mention alignment",
                "SIMD/vectorization involvement alone does not prove an alignment issue",
            ],
            missing_context=missing,
            recommended_next_steps=_next_steps_for_label("alignment_plausible_not_proven"),
        )

    if _is_simd_vectorization_involved(record):
        return AlignmentClassification(
            alignment_label="alignment_plausible_not_proven",
            alignment_confidence="medium",
            evidence_reasons=[
                "SIMD/vectorization is involved but the remark does not prove alignment is the issue",
            ],
            missing_context=missing,
            recommended_next_steps=_next_steps_for_label("alignment_plausible_not_proven"),
        )

    if not text.strip():
        return AlignmentClassification(
            alignment_label="insufficient_evidence",
            alignment_confidence="low",
            evidence_reasons=[
                "heuristic slice matched but remark text is empty or too sparse to classify alignment",
            ],
            missing_context=missing,
            recommended_next_steps=_next_steps_for_label("insufficient_evidence"),
        )

    return AlignmentClassification(
        alignment_label="insufficient_evidence",
        alignment_confidence="low",
        evidence_reasons=[
            "heuristic slice matched but no explicit alignment or alternative-cause vocabulary found",
        ],
        missing_context=missing,
        recommended_next_steps=_next_steps_for_label("insufficient_evidence"),
    )
