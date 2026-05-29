"""Training data export for the future ML ranker."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from explncc.cli import app
from explncc.local.features import FEATURE_NAMES
from explncc.local.training_export import build_training_rows, render_training_rows
from explncc.models import OptimizationRecord

runner = CliRunner()

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "inline_miss_no_definition.opt.yaml"


def _rec(**kw: object) -> OptimizationRecord:
    return OptimizationRecord(**kw)  # type: ignore[arg-type]


def test_row_schema() -> None:
    rec = _rec(
        kind="missed",
        pass_name="loop-vectorize",
        message="cannot prove memory independence",
        record_id="r1",
    )
    rows = build_training_rows([rec])
    row = rows[0]
    assert set(row.keys()) == {
        "record_id",
        "features",
        "rule_label",
        "rule_confidence",
        "score",
        "text",
        "metadata",
    }
    assert row["rule_label"] == "vectorize_aliasing"
    assert row["rule_confidence"] == "high"
    assert 0.0 <= row["score"] <= 1.0
    assert set(row["features"].keys()) == set(FEATURE_NAMES)


def test_unknown_label_source_raises() -> None:
    rec = _rec(kind="missed", pass_name="inline", message="no definition")
    try:
        build_training_rows([rec], include_labels_from="bogus")
    except ValueError as exc:
        assert "label source" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_render_jsonl_roundtrip() -> None:
    rec = _rec(kind="missed", pass_name="inline", message="no definition", record_id="r1")
    rows = build_training_rows([rec])
    text = render_training_rows(rows, "jsonl")
    parsed = [json.loads(line) for line in text.splitlines() if line.strip()]
    assert parsed[0]["record_id"] == "r1"


def test_render_csv_has_feature_columns() -> None:
    rec = _rec(kind="missed", pass_name="inline", message="no definition")
    rows = build_training_rows([rec])
    text = render_training_rows(rows, "csv")
    header = text.splitlines()[0]
    assert "feat_kind_is_missed" in header
    assert "rule_label" in header


def test_cli_export_training_jsonl(tmp_path: Path) -> None:
    out = tmp_path / "training.jsonl"
    result = runner.invoke(
        app,
        [
            "export-training",
            str(FIXTURE),
            "--include-labels-from",
            "rules",
            "--format",
            "jsonl",
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 0
    assert out.is_file()
    lines = [ln for ln in out.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert "features" in first
    assert "rule_label" in first


def test_cli_export_training_bad_format() -> None:
    result = runner.invoke(app, ["export-training", str(FIXTURE), "--format", "parquet"])
    assert result.exit_code == 2
