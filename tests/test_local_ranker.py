"""Deterministic weighted local ranker."""

from __future__ import annotations

from explncc.local.classifier import classify_record
from explncc.local.features import extract_features
from explncc.local.ranker import LocalRankerV1, _score_one, rank_records
from explncc.models import OptimizationRecord


def _rec(**kw: object) -> OptimizationRecord:
    return OptimizationRecord(**kw)  # type: ignore[arg-type]


def _score(
    rec: OptimizationRecord,
    *,
    cluster_size: int = 1,
    include_passed: bool = False,
) -> float:
    classification = classify_record(rec)
    fx = extract_features(rec)
    score, _reasons = _score_one(
        rec,
        classification,
        fx,
        cluster_size=cluster_size,
        include_passed=include_passed,
    )
    return score


def test_aliasing_miss_scores_high() -> None:
    rec = _rec(
        kind="missed",
        pass_name="loop-vectorize",
        message="cannot prove memory independence",
        file="a.cpp",
        line=10,
    )
    # +30 missed, +25 lv miss, +20 aliasing, +5 source loc = 80
    assert _score(rec) == 80.0


def test_passed_remark_penalized_unless_included() -> None:
    rec = _rec(
        kind="passed",
        pass_name="loop-vectorize",
        remark_name="Vectorized",
        file="a.cpp",
        line=2,
    )
    penalized = _score(rec, include_passed=False)
    included = _score(rec, include_passed=True)
    assert included > penalized
    assert included - penalized == 20.0


def test_passed_to_missed_change_boosts_score() -> None:
    from explncc.local.features import DiffContext

    rec = _rec(
        kind="missed",
        pass_name="loop-vectorize",
        message="cannot prove memory independence",
    )
    findings = LocalRankerV1().rank_records(
        [rec],
        diffs=[DiffContext(changed_from_passed_to_missed=True)],
    )
    assert any("+40" in r for r in findings[0].score_reasons)


def test_ranking_order_and_ranks_assigned() -> None:
    aliasing = _rec(
        kind="missed",
        pass_name="loop-vectorize",
        message="cannot prove memory independence",
        file="a.cpp",
        line=10,
        function="hot",
    )
    analysis = _rec(kind="analysis", pass_name="prologepilog", message="0 stack bytes")
    findings = rank_records([analysis, aliasing])
    assert findings[0].record is aliasing
    assert findings[0].rank == 1
    assert findings[1].rank == 2
    assert findings[0].score > findings[1].score


def test_severity_mapping() -> None:
    rec = _rec(
        kind="missed",
        pass_name="loop-vectorize",
        message="cannot prove memory independence",
        file="a.cpp",
        line=10,
    )
    findings = rank_records([rec])
    # score 80 -> high
    assert findings[0].severity == "high"
    assert 0.0 <= findings[0].normalized_score <= 1.0


def test_score_reasons_are_explainable() -> None:
    rec = _rec(
        kind="missed",
        pass_name="loop-vectorize",
        message="cannot prove memory independence",
        file="a.cpp",
        line=10,
    )
    findings = rank_records([rec])
    reasons = findings[0].score_reasons
    assert any("Missed" in r for r in reasons)
    assert any("loop-vectorize" in r for r in reasons)
    assert any("memory independence" in r or "aliasing" in r for r in reasons)


def test_deterministic_repeated_runs() -> None:
    recs = [
        _rec(kind="missed", pass_name="loop-vectorize", message="cannot prove memory independence",
             record_id="r1"),
        _rec(kind="missed", pass_name="inline", message="too costly", record_id="r2"),
    ]
    a = [f.to_dict(include_record=False) for f in rank_records(recs)]
    b = [f.to_dict(include_record=False) for f in rank_records(recs)]
    assert a == b
