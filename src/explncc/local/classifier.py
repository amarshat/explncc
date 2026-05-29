"""Rule-based local classifier over normalized optimization records.

The classifier is deterministic and conservative: when evidence is weak it
returns ``insufficient_evidence`` or a generic label rather than overclaiming.
It never invents compiler facts, and it does not attribute a miss to alignment
unless the command focus is alignment.

No network, no model backend.
"""

from __future__ import annotations

from typing import Any

from explncc.evidence import EvidencePack
from explncc.local.contracts import ClassificationResult, Confidence
from explncc.local.taxonomy import get_label
from explncc.models import OptimizationRecord

# Focus controls whether alignment-specific labels are eligible. Alignment is
# only asserted as a hypothesis when the caller explicitly asked for it.
ClassifyFocus = str | None

_ALIAS_MARKERS: tuple[str, ...] = (
    "cannot prove memory independence",
    "memory independence",
    "memory dependence",
    "may alias",
    "aliasing",
    "alias",
    "cannot prove pointer",
    "cannot identify array bounds",
)

_COST_MARKERS: tuple[str, ...] = (
    "not beneficial",
    "not profitable",
    "unprofitable",
    "cost-model",
    "cost model",
    "cost",
    "threshold",
)

_CALL_MARKERS: tuple[str, ...] = (
    "call in loop",
    "function call",
    "call cannot be",
    "cannot vectorize calls",
    "call instruction",
)

_TRIP_COUNT_MARKERS: tuple[str, ...] = (
    "trip count",
    "tripcount",
    "loop count",
    "backedge",
    "iteration count",
)

_NO_DEFINITION_MARKERS: tuple[str, ...] = (
    "nodefinition",
    "definition is unavailable",
    "definition unavailable",
    "no definition",
)

_INLINE_COST_MARKERS: tuple[str, ...] = (
    "too costly",
    "cost",
    "threshold",
    "not inlined into",
)

_ALIGNMENT_EXPLICIT_MARKERS: tuple[str, ...] = (
    "misaligned",
    "unaligned",
    "aligned load",
    "aligned store",
    "aligned access",
    "alignment",
    "assume_aligned",
)

_VECTOR_INVOLVED_MARKERS: tuple[str, ...] = (
    "vectoriz",
    "simd",
    "interleave",
)

_WASM_MARKERS: tuple[str, ...] = ("wasm", "webassembly")
_NEON_MARKERS: tuple[str, ...] = ("neon", "aarch64")
_AVX_MARKERS: tuple[str, ...] = ("avx", "avx2", "avx512", "avx-512", " sse")

_DEFAULT_MISSING_CONTEXT: tuple[str, ...] = (
    "source_snippet",
    "ir_snippet",
    "assembly_snippet",
    "target_triple",
)


def _args_text(args_raw: Any) -> str:
    """Flatten ``args_raw`` (list/dict/str) into a single lowercased string."""

    if args_raw is None:
        return ""
    if isinstance(args_raw, str):
        return args_raw.lower()
    if isinstance(args_raw, dict):
        return " ".join(_args_text(v) for v in args_raw.values())
    if isinstance(args_raw, (list, tuple)):
        return " ".join(_args_text(v) for v in args_raw)
    return str(args_raw).lower()


def _record_text(record: OptimizationRecord) -> str:
    parts = [
        record.message or "",
        record.remark_name or "",
        record.reason or "",
        _args_text(record.args_raw),
    ]
    return " ".join(p for p in parts if p).lower()


def _any(text: str, markers: tuple[str, ...]) -> str | None:
    for m in markers:
        if m in text:
            return m
    return None


def _pass(record: OptimizationRecord) -> str:
    return (record.pass_name or "").lower()


def _missing_context_from_pack(pack: EvidencePack | None) -> list[str]:
    if pack is not None:
        return list(pack.missing_context)
    return list(_DEFAULT_MISSING_CONTEXT)


def _result(
    label_id: str,
    confidence: Confidence,
    *,
    score_hint: float,
    evidence_reasons: list[str],
    missing_context: list[str],
    extra_actions: list[str] | None = None,
) -> ClassificationResult:
    label = get_label(label_id)
    actions = list(label.recommended_actions)
    if extra_actions:
        actions = actions + [a for a in extra_actions if a not in actions]
    return ClassificationResult(
        label=label_id,
        confidence=confidence,
        score_hint=score_hint,
        evidence_reasons=evidence_reasons,
        missing_context=missing_context,
        recommended_actions=actions,
    )


def _classify_inline(
    record: OptimizationRecord,
    text: str,
    missing: list[str],
) -> ClassificationResult | None:
    if _any(text, _NO_DEFINITION_MARKERS):
        return _result(
            "inline_no_definition",
            "high",
            score_hint=0.7,
            evidence_reasons=[
                "pass is inline",
                "remark indicates the callee definition is unavailable",
            ],
            missing_context=missing,
        )
    if record.kind == "passed":
        return _result(
            "inline_success",
            "medium",
            score_hint=0.2,
            evidence_reasons=["pass is inline", "remark kind is Passed (successful inline)"],
            missing_context=missing,
        )
    cost = _any(text, _INLINE_COST_MARKERS)
    if cost is not None:
        return _result(
            "inline_too_costly",
            "high",
            score_hint=0.5,
            evidence_reasons=[
                "pass is inline",
                f"remark mentions inline cost / threshold ({cost!r})",
            ],
            missing_context=missing,
        )
    return None


def _classify_vectorize(
    record: OptimizationRecord,
    text: str,
    missing: list[str],
) -> ClassificationResult | None:
    if record.kind == "passed" or (record.remark_name or "") == "Vectorized":
        return _result(
            "vectorize_success",
            "medium",
            score_hint=0.15,
            evidence_reasons=["pass is a vectorizer", "remark indicates successful vectorization"],
            missing_context=missing,
        )
    if record.kind != "missed":
        return None
    alias = _any(text, _ALIAS_MARKERS)
    if alias is not None:
        return _result(
            "vectorize_aliasing",
            "high",
            score_hint=0.8,
            evidence_reasons=[
                "pass is a vectorizer",
                "remark kind is Missed",
                f"message mentions memory independence / aliasing ({alias!r})",
            ],
            missing_context=missing,
        )
    call = _any(text, _CALL_MARKERS)
    if call is not None:
        return _result(
            "vectorize_call_in_loop",
            "high",
            score_hint=0.6,
            evidence_reasons=[
                "pass is a vectorizer",
                "remark kind is Missed",
                f"message mentions a call in the loop ({call!r})",
            ],
            missing_context=missing,
        )
    trip = _any(text, _TRIP_COUNT_MARKERS)
    if trip is not None:
        return _result(
            "vectorize_unknown_trip_count",
            "medium",
            score_hint=0.45,
            evidence_reasons=[
                "pass is a vectorizer",
                "remark kind is Missed",
                f"message mentions trip count ({trip!r})",
            ],
            missing_context=missing,
        )
    cost = _any(text, _COST_MARKERS)
    if cost is not None:
        return _result(
            "vectorize_cost_rejected",
            "high",
            score_hint=0.4,
            evidence_reasons=[
                "pass is a vectorizer",
                "remark kind is Missed",
                f"message mentions cost / profitability ({cost!r})",
            ],
            missing_context=missing,
        )
    return None


def _classify_unroll(
    record: OptimizationRecord,
    text: str,
    missing: list[str],
) -> ClassificationResult | None:
    if record.kind != "missed":
        return None
    trip = _any(text, _TRIP_COUNT_MARKERS)
    if trip is not None:
        return _result(
            "unroll_unknown_trip_count",
            "medium",
            score_hint=0.35,
            evidence_reasons=[
                "pass is loop-unroll",
                "remark kind is Missed",
                f"message mentions trip count ({trip!r})",
            ],
            missing_context=missing,
        )
    cost = _any(text, _COST_MARKERS)
    if cost is not None:
        return _result(
            "unroll_cost_rejected",
            "medium",
            score_hint=0.3,
            evidence_reasons=[
                "pass is loop-unroll",
                "remark kind is Missed",
                f"message mentions cost / threshold ({cost!r})",
            ],
            missing_context=missing,
        )
    return None


def _classify_target_specific(
    record: OptimizationRecord,
    pack: EvidencePack | None,
    text: str,
    missing: list[str],
) -> ClassificationResult | None:
    """Target-specific labels only fire with explicit target evidence.

    We require an actual target triple/cpu (from the evidence pack or tool
    metadata) so we never invent ISA details from message wording alone.
    """

    target_blob_parts: list[str] = []
    if pack is not None:
        target_blob_parts.extend(
            x for x in (pack.target_triple, pack.cpu, pack.march) if x
        )
    meta = record.tool_version_metadata or {}
    target_blob_parts.extend(str(v) for v in meta.values())
    target_blob = " ".join(target_blob_parts).lower()
    if not target_blob:
        return None

    if _any(target_blob, _WASM_MARKERS) and _any(text, _VECTOR_INVOLVED_MARKERS):
        return _result(
            "wasm_simd_limitation",
            "medium",
            score_hint=0.4,
            evidence_reasons=["target evidence indicates WebAssembly", "SIMD is involved"],
            missing_context=missing,
        )
    if _any(target_blob, _NEON_MARKERS) and _any(text, _VECTOR_INVOLVED_MARKERS):
        return _result(
            "arm_neon_difference",
            "low",
            score_hint=0.3,
            evidence_reasons=["target evidence indicates ARM/NEON", "SIMD is involved"],
            missing_context=missing,
        )
    if _any(target_blob, _AVX_MARKERS) and _any(text, _VECTOR_INVOLVED_MARKERS):
        return _result(
            "x86_avx_difference",
            "low",
            score_hint=0.3,
            evidence_reasons=["target evidence indicates x86 AVX/SSE", "SIMD is involved"],
            missing_context=missing,
        )
    return None


def _classify_alignment_focus(
    record: OptimizationRecord,
    text: str,
    missing: list[str],
) -> ClassificationResult | None:
    """Alignment labels, eligible only when the command focus is alignment."""

    marker = _any(text, _ALIGNMENT_EXPLICIT_MARKERS)
    if marker is not None:
        return _result(
            "alignment_explicit",
            "high",
            score_hint=0.5,
            evidence_reasons=[f"remark explicitly mentions alignment vocabulary ({marker!r})"],
            missing_context=missing,
        )
    if record.vectorization_factor is not None or _any(text, _VECTOR_INVOLVED_MARKERS):
        return _result(
            "alignment_plausible_not_proven",
            "low",
            score_hint=0.2,
            evidence_reasons=[
                "SIMD/vectorization is involved but the remark does not prove "
                "alignment is the issue",
            ],
            missing_context=missing,
        )
    return None


def _fallback(
    record: OptimizationRecord,
    text: str,
    missing: list[str],
) -> ClassificationResult:
    if not text.strip():
        return _result(
            "insufficient_evidence",
            "low",
            score_hint=0.05,
            evidence_reasons=["remark text is empty or too sparse to classify"],
            missing_context=missing,
        )
    if record.kind == "missed":
        return _result(
            "generic_missed_optimization",
            "low",
            score_hint=0.25,
            evidence_reasons=[
                "remark kind is Missed but no specific local rule matched",
            ],
            missing_context=missing,
        )
    if record.kind == "analysis":
        return _result(
            "generic_analysis",
            "low",
            score_hint=0.05,
            evidence_reasons=["remark kind is Analysis"],
            missing_context=missing,
        )
    if record.kind == "passed":
        return _result(
            "generic_passed",
            "low",
            score_hint=0.05,
            evidence_reasons=["remark kind is Passed"],
            missing_context=missing,
        )
    return _result(
        "insufficient_evidence",
        "low",
        score_hint=0.05,
        evidence_reasons=["remark did not match any specific local rule"],
        missing_context=missing,
    )


def classify_record(
    record: OptimizationRecord,
    *,
    pack: EvidencePack | None = None,
    focus: ClassifyFocus = None,
) -> ClassificationResult:
    """Classify one normalized remark into a local label (deterministic).

    ``focus`` enables alignment-specific labels only when set to ``"alignment"``.
    When evidence is weak, the result falls back to a generic label or
    ``insufficient_evidence`` rather than overclaiming.
    """

    text = _record_text(record)
    missing = _missing_context_from_pack(pack)
    pass_l = _pass(record)

    if "inline" in pass_l:
        res = _classify_inline(record, text, missing)
        if res is not None:
            return res

    if "vector" in pass_l:
        res = _classify_vectorize(record, text, missing)
        if res is not None:
            return res

    if "unroll" in pass_l:
        res = _classify_unroll(record, text, missing)
        if res is not None:
            return res

    target_res = _classify_target_specific(record, pack, text, missing)
    if target_res is not None:
        return target_res

    if (focus or "").strip().lower() == "alignment":
        align_res = _classify_alignment_focus(record, text, missing)
        if align_res is not None:
            return align_res

    return _fallback(record, text, missing)


def classify_records(
    records: list[OptimizationRecord],
    *,
    focus: ClassifyFocus = None,
) -> list[ClassificationResult]:
    """Classify a batch of records preserving input order."""

    return [classify_record(r, focus=focus) for r in records]
