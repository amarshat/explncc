"""SIMD / alignment heuristic slice."""

from __future__ import annotations

from explncc.alignment import alignment_signals, filter_alignment_related, is_alignment_related
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
