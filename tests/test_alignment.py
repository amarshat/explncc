"""SIMD / alignment heuristic slice and evidence classification."""

from __future__ import annotations

from explncc.alignment import (
    alignment_signals,
    classify_alignment,
    filter_alignment_related,
    is_alignment_related,
)
from explncc.models import OptimizationRecord


def test_loop_vectorize_pass_emits_signal() -> None:
    r = OptimizationRecord(
        kind="passed",
        pass_name="loop-vectorize",
        remark_name="Vectorized",
        message="vectorized loop",
    )
    sig = alignment_signals(r)
    assert "pass:loop-vectorize" in sig
    assert is_alignment_related(r)


def test_alignment_word_in_message() -> None:
    r = OptimizationRecord(
        kind="missed",
        pass_name="gvn",
        remark_name="X",
        message="load not vectorized due to alignment",
    )
    assert any(s.startswith("msg:") for s in alignment_signals(r))


def test_filter_keeps_only_related() -> None:
    a = OptimizationRecord(kind="passed", pass_name="loop-vectorize", remark_name="Vectorized")
    b = OptimizationRecord(kind="missed", pass_name="inline", remark_name="NoDefinition")
    out = filter_alignment_related([a, b])
    assert len(out) == 1
    assert out[0].pass_name == "loop-vectorize"


def test_vectorized_with_factor_is_plausible_not_proven() -> None:
    r = OptimizationRecord(
        kind="passed",
        pass_name="loop-vectorize",
        remark_name="Vectorized",
        message="vectorized loop",
        vectorization_factor=4,
    )
    c = classify_alignment(r)
    assert c.alignment_label == "alignment_plausible_not_proven"
    assert c.alignment_confidence == "medium"
    assert any("vectorization" in reason.lower() for reason in c.evidence_reasons)


def test_explicit_aligned_intrinsic() -> None:
    r = OptimizationRecord(
        kind="passed",
        pass_name="loop-vectorize",
        remark_name="Vectorized",
        message="vectorized using _mm256_load_ps",
        vectorization_factor=8,
    )
    c = classify_alignment(r)
    assert c.alignment_label == "alignment_explicit"
    assert c.alignment_confidence == "high"
    assert any("_mm256_load_ps" in reason for reason in c.evidence_reasons)


def test_explicit_unaligned_intrinsic() -> None:
    r = OptimizationRecord(
        kind="passed",
        pass_name="loop-vectorize",
        remark_name="Vectorized",
        message="vectorized using _mm256_loadu_ps",
        vectorization_factor=8,
    )
    c = classify_alignment(r)
    assert c.alignment_label == "alignment_explicit"
    assert any("_mm256_loadu_ps" in reason for reason in c.evidence_reasons)


def test_aliasing_not_alignment() -> None:
    r = OptimizationRecord(
        kind="missed",
        pass_name="loop-vectorize",
        remark_name="MissedDetails",
        message="cannot prove memory independence",
    )
    c = classify_alignment(r)
    assert c.alignment_label == "alignment_unlikely_from_evidence"
    assert c.alignment_confidence == "high"
    assert any("aliasing" in reason.lower() for reason in c.evidence_reasons)
    assert "source_snippet" in c.missing_context
    assert any("restrict" in step.lower() for step in c.recommended_next_steps)


def test_cost_not_alignment() -> None:
    r = OptimizationRecord(
        kind="missed",
        pass_name="loop-vectorize",
        remark_name="NotBeneficial",
        message="cost threshold prevents vectorization",
    )
    c = classify_alignment(r)
    assert c.alignment_label == "alignment_unlikely_from_evidence"
    assert any("cost" in reason.lower() for reason in c.evidence_reasons)


def test_not_alignment_related() -> None:
    r = OptimizationRecord(
        kind="missed",
        pass_name="inline",
        remark_name="NoDefinition",
        message="no definition",
    )
    c = classify_alignment(r)
    assert c.alignment_label == "not_alignment_related"
    assert c.alignment_confidence == "high"


def test_missing_context_populated() -> None:
    r = OptimizationRecord(
        kind="passed",
        pass_name="loop-vectorize",
        remark_name="Vectorized",
        message="vectorized loop",
        vectorization_factor=4,
    )
    c = classify_alignment(r)
    for field in ("source_snippet", "ir_snippet", "assembly_snippet", "target_triple"):
        assert field in c.missing_context


def test_classification_to_dict() -> None:
    r = OptimizationRecord(
        kind="missed",
        pass_name="loop-vectorize",
        remark_name="MissedDetails",
        message="cannot prove memory independence",
    )
    d = classify_alignment(r).to_dict()
    assert d["alignment_label"] == "alignment_unlikely_from_evidence"
    assert isinstance(d["evidence_reasons"], list)
    assert isinstance(d["missing_context"], list)
    assert isinstance(d["recommended_next_steps"], list)
