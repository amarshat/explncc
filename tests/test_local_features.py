"""Feature extraction for the local ranker."""

from __future__ import annotations

from explncc.local.features import FEATURE_NAMES, DiffContext, extract_features
from explncc.models import OptimizationRecord


def _rec(**kw: object) -> OptimizationRecord:
    return OptimizationRecord(**kw)  # type: ignore[arg-type]


def test_basic_missed_vectorize_features() -> None:
    rec = _rec(
        kind="missed",
        pass_name="loop-vectorize",
        message="cannot prove memory independence",
        function="process_sensor",
        file="a.cpp",
        line=10,
    )
    fx = extract_features(rec)
    f = fx.features
    assert f["kind_is_missed"] == 1
    assert f["pass_loop_vectorize"] == 1
    assert f["msg_memory_independence"] == 1
    assert f["msg_alias"] == 0  # "memory independence" should not set alias unless 'alias' present
    assert f["has_source_location"] == 1
    assert f["has_debug_location"] == 1
    assert f["function_name_present"] == 1


def test_reasons_are_human_readable() -> None:
    rec = _rec(
        kind="missed",
        pass_name="loop-vectorize",
        message="cannot prove memory independence",
    )
    fx = extract_features(rec)
    assert "remark kind is Missed" in fx.reasons
    assert any("memory independence" in r for r in fx.reasons)


def test_all_feature_names_present_and_zero_default() -> None:
    rec = _rec(kind="analysis", pass_name="prologepilog")
    fx = extract_features(rec)
    assert set(fx.features.keys()) == set(FEATURE_NAMES)
    # Analysis remark with no message => most signals off.
    assert fx.features["kind_is_analysis"] == 1
    assert fx.features["msg_cost"] == 0


def test_diff_features_applied() -> None:
    rec = _rec(kind="missed", pass_name="loop-vectorize", message="not beneficial")
    diff = DiffContext(
        appeared_in_current_build=True,
        changed_from_passed_to_missed=True,
    )
    fx = extract_features(rec, diff=diff)
    assert fx.features["appeared_in_current_build"] == 1
    assert fx.features["changed_from_passed_to_missed"] == 1
    assert fx.features["disappeared_from_baseline"] == 0
    assert "appeared in the current build" in fx.reasons


def test_interleave_count_feature() -> None:
    rec = _rec(
        kind="passed",
        pass_name="loop-vectorize",
        args_raw=[{"InterleaveCount": "2"}],
    )
    fx = extract_features(rec)
    assert fx.features["has_interleave_count"] == 1
