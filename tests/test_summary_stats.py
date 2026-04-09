"""Summary filters and stats aggregates."""

from __future__ import annotations

from pathlib import Path

from explncc.normalizer import load_records_from_path
from explncc.stats import aggregate
from explncc.summary import apply_filters, rows_for_table

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "inline_miss_no_definition.opt.yaml"


def test_apply_filters_pass_and_kind() -> None:
    recs = load_records_from_path(FIXTURE)
    only_inline = apply_filters(recs, pass_contains="inline")
    assert all(r.pass_name and "inline" in r.pass_name.lower() for r in only_inline)
    missed = apply_filters(recs, kind="missed")
    assert all(r.kind == "missed" for r in missed)


def test_rows_for_table_truncation() -> None:
    recs = load_records_from_path(FIXTURE)
    rows = rows_for_table(recs, max_message=10)
    assert rows
    assert all(len(r[5]) <= 11 for r in rows)  # ellipsis adds one char


def test_aggregate_keys() -> None:
    recs = load_records_from_path(FIXTURE)
    stats = aggregate(recs)
    assert stats["total"] == len(recs)
    assert "inline" in stats["by_pass"]
