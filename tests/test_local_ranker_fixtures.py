"""End-to-end local pipeline over offline .opt.yaml fixtures.

Parses real fixtures (no network), classifies them, and asserts both the
expected labels and the relative rank order produced by LocalRankerV1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from explncc.local.classifier import classify_record
from explncc.local.ranker import rank_records
from explncc.normalizer import load_records_from_path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "local_ranker"

EXPECTED_LABELS = {
    "vectorize_aliasing": "vectorize_aliasing",
    "vectorize_cost_rejected": "vectorize_cost_rejected",
    "inline_no_definition": "inline_no_definition",
    "inline_too_costly": "inline_too_costly",
    "vectorize_success": "vectorize_success",
    "generic_analysis": "generic_analysis",
    "insufficient_evidence": "insufficient_evidence",
}


@pytest.mark.parametrize(("stem", "expected"), sorted(EXPECTED_LABELS.items()))
def test_fixture_classifies_to_expected_label(stem: str, expected: str) -> None:
    records = load_records_from_path(FIXTURES / f"{stem}.opt.yaml")
    assert records, f"no records parsed from {stem}.opt.yaml"
    # The first (primary) remark in each fixture carries the label under test.
    result = classify_record(records[0])
    assert result.label == expected


def test_rank_order_across_fixtures() -> None:
    records = load_records_from_path(FIXTURES)
    findings = rank_records(records)
    label_to_score = {f.label: f.score for f in findings}

    # Aliasing miss must outrank a cost-only miss, which outranks success and analysis.
    assert label_to_score["vectorize_aliasing"] > label_to_score["vectorize_cost_rejected"]
    assert label_to_score["vectorize_cost_rejected"] > label_to_score["vectorize_success"]
    assert label_to_score["inline_no_definition"] > label_to_score["generic_analysis"]

    # Highest-ranked finding overall should be the aliasing miss.
    assert findings[0].label == "vectorize_aliasing"
    assert findings[0].rank == 1


def test_ranks_are_contiguous_and_sorted() -> None:
    records = load_records_from_path(FIXTURES)
    findings = rank_records(records)
    assert [f.rank for f in findings] == list(range(1, len(findings) + 1))
    scores = [f.score for f in findings]
    assert scores == sorted(scores, reverse=True)


def test_success_fixture_has_interleave_and_vf() -> None:
    records = load_records_from_path(FIXTURES / "vectorize_success.opt.yaml")
    rec = records[0]
    assert rec.vectorization_factor == 4
    assert rec.kind == "passed"
