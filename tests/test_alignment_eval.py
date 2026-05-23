"""Tests for eval-alignment heuristic scoring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from explncc.alignment_eval import (
    detect_overreach,
    evaluate_predictions,
    load_predictions_jsonl,
    score_prediction,
)
from explncc.alignment_eval_output import render_eval_report
from explncc.cli import app

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "alignment_predictions.jsonl"
RUNNER = CliRunner()


def test_load_predictions_jsonl() -> None:
    rows = load_predictions_jsonl(FIXTURE)
    assert len(rows) == 3


def test_good_output_scores_higher_than_overreach() -> None:
    rows = load_predictions_jsonl(FIXTURE)
    good = score_prediction(rows[0])
    bad = score_prediction(rows[1])
    assert good.total > bad.total
    assert bad.overreach_penalty < 0
    assert bad.alignment_discipline == 0


def test_detect_avx2_without_target() -> None:
    row = {
        "expected_alignment_label": "alignment_plausible_not_proven",
        "evidence": {"pass_name": "loop-vectorize"},
    }
    hits = detect_overreach(row, "AVX2 failed due to alignment.")
    assert any(h.category == "invented_target" for h in hits)


def test_evaluate_aggregate_report() -> None:
    report = evaluate_predictions(load_predictions_jsonl(FIXTURE))
    assert len(report.samples) == 3
    assert report.aggregate_score > 0
    assert report.failure_categories
    assert report.overreach_examples


def test_render_json_and_markdown() -> None:
    report = evaluate_predictions(load_predictions_jsonl(FIXTURE))
    js = render_eval_report(report, "json")
    assert '"aggregate_score"' in js
    md = render_eval_report(report, "markdown")
    assert "# Alignment evaluation report" in md
    assert "Overreach examples" in md


def test_render_unknown_format_raises() -> None:
    report = evaluate_predictions(load_predictions_jsonl(FIXTURE))
    with pytest.raises(ValueError, match="unknown eval format"):
        render_eval_report(report, "xml")


def test_cli_eval_alignment_markdown(tmp_path: Path) -> None:
    out = tmp_path / "report.md"
    result = RUNNER.invoke(
        app,
        ["eval-alignment", str(FIXTURE), "--format", "markdown", "--output", str(out)],
    )
    assert result.exit_code == 0
    assert out.is_file()
    assert "Alignment evaluation report" in out.read_text(encoding="utf-8")


def test_cli_eval_alignment_json_stdout() -> None:
    result = RUNNER.invoke(app, ["eval-alignment", str(FIXTURE), "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data["samples"]) == 3
