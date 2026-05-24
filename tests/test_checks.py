"""CI check rules."""

from __future__ import annotations

from pathlib import Path

from explncc.checks import run_checks
from explncc.normalizer import load_records_from_path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "inline_miss_no_definition.opt.yaml"


def test_check_passes_with_high_thresholds() -> None:
    recs = load_records_from_path(FIXTURE)
    result = run_checks(
        recs,
        max_missed_loop_vectorize=1000,
        max_missed_inline=1000,
    )
    assert result.ok


def test_check_fails_on_tight_inline_cap() -> None:
    recs = load_records_from_path(FIXTURE)
    result = run_checks(recs, max_missed_inline=0)
    assert not result.ok
    assert result.violations


def test_build_policy_result_contributors() -> None:
    from explncc.checks import build_policy_result

    recs = load_records_from_path(FIXTURE)
    policy = build_policy_result(recs, max_missed_inline=0)
    assert policy is not None
    assert policy.status == "fail"
    assert policy.thresholds[0].contributors
