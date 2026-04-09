"""Diff engine between record sets."""

from __future__ import annotations

from pathlib import Path

from explncc.diffing import diff_records
from explncc.normalizer import load_records_from_path

FIXTURE_A = Path(__file__).resolve().parent / "fixtures" / "inline_miss_no_definition.opt.yaml"
FIXTURE_B = Path(__file__).resolve().parent / "fixtures" / "tiny_passed.opt.yaml"


def test_diff_new_and_resolved_missed() -> None:
    before = load_records_from_path(FIXTURE_A)
    after = load_records_from_path(FIXTURE_B)
    report = diff_records(before, after)
    assert any(r.remark_name == "NoDefinition" for r in report.resolved_missed)
    assert not any(r.remark_name == "NoDefinition" for r in report.new_missed)
