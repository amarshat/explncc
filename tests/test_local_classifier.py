"""Rule-based local classifier behavior."""

from __future__ import annotations

from explncc.local.classifier import classify_record
from explncc.models import OptimizationRecord


def _rec(**kw: object) -> OptimizationRecord:
    return OptimizationRecord(**kw)  # type: ignore[arg-type]


def test_vectorize_aliasing_high_confidence() -> None:
    rec = _rec(
        kind="missed",
        pass_name="loop-vectorize",
        message="loop not vectorized: cannot prove memory independence",
        function="process_sensor",
    )
    res = classify_record(rec)
    assert res.label == "vectorize_aliasing"
    assert res.confidence == "high"
    assert any("independence" in r.lower() or "alias" in r.lower() for r in res.evidence_reasons)


def test_vectorize_cost_rejected() -> None:
    rec = _rec(
        kind="missed",
        pass_name="loop-vectorize",
        message="loop not vectorized: vectorization is not beneficial and is not profitable",
    )
    res = classify_record(rec)
    assert res.label == "vectorize_cost_rejected"


def test_vectorize_call_in_loop_before_cost() -> None:
    rec = _rec(
        kind="missed",
        pass_name="loop-vectorize",
        message="loop not vectorized: call in loop cannot be vectorized",
    )
    res = classify_record(rec)
    assert res.label == "vectorize_call_in_loop"


def test_inline_no_definition() -> None:
    rec = _rec(
        kind="missed",
        pass_name="inline",
        remark_name="NoDefinition",
        message="will not be inlined because its definition is unavailable",
    )
    res = classify_record(rec)
    assert res.label == "inline_no_definition"
    assert res.confidence == "high"


def test_inline_too_costly() -> None:
    rec = _rec(
        kind="missed",
        pass_name="inline",
        message="not inlined into caller because too costly (cost=200, threshold=100)",
    )
    res = classify_record(rec)
    assert res.label == "inline_too_costly"


def test_vectorize_success() -> None:
    rec = _rec(kind="passed", pass_name="loop-vectorize", remark_name="Vectorized")
    res = classify_record(rec)
    assert res.label == "vectorize_success"
    assert res.confidence == "medium"


def test_unroll_unknown_trip_count() -> None:
    rec = _rec(
        kind="missed",
        pass_name="loop-unroll",
        message="unable to fully unroll loop with unknown trip count",
    )
    res = classify_record(rec)
    assert res.label == "unroll_unknown_trip_count"


def test_generic_analysis_for_analysis_kind() -> None:
    rec = _rec(kind="analysis", pass_name="prologepilog", message="0 stack bytes in function")
    res = classify_record(rec)
    assert res.label == "generic_analysis"


def test_insufficient_evidence_when_empty() -> None:
    rec = _rec(kind="missed", pass_name="some-pass")
    res = classify_record(rec)
    assert res.label == "insufficient_evidence"


def test_generic_missed_when_no_rule_matches() -> None:
    rec = _rec(kind="missed", pass_name="gvn", message="something opaque happened here")
    res = classify_record(rec)
    assert res.label == "generic_missed_optimization"


def test_no_alignment_overclaim_without_focus() -> None:
    # SIMD involved but focus is not alignment: must not assert alignment.
    rec = _rec(
        kind="passed",
        pass_name="loop-vectorize",
        remark_name="Vectorized",
        vectorization_factor=4,
    )
    res = classify_record(rec, focus=None)
    assert res.label != "alignment_plausible_not_proven"


def test_alignment_plausible_only_with_focus() -> None:
    rec = _rec(
        kind="analysis",
        pass_name="loop-vectorize",
        message="vectorization analysis for loop",
        vectorization_factor=4,
    )
    res = classify_record(rec, focus="alignment")
    assert res.label == "alignment_plausible_not_proven"
    assert res.confidence == "low"


def test_alignment_explicit_with_focus() -> None:
    rec = _rec(
        kind="missed",
        pass_name="loop-vectorize",
        message="loop not vectorized due to unaligned access",
    )
    res = classify_record(rec, focus="alignment")
    assert res.label == "alignment_explicit"


def test_target_specific_requires_target_evidence() -> None:
    # Mentions SIMD but no target metadata -> must not assert wasm/neon/avx.
    rec = _rec(kind="missed", pass_name="loop-vectorize", message="simd lowering issue")
    res = classify_record(rec)
    assert res.label not in {"wasm_simd_limitation", "arm_neon_difference", "x86_avx_difference"}
