"""CLI tests for the offline local commands: classify and rank."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from explncc.cli import app

runner = CliRunner()

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "inline_miss_no_definition.opt.yaml"


def test_classify_table() -> None:
    result = runner.invoke(app, ["classify", str(FIXTURE), "--local", "--format", "table"])
    assert result.exit_code == 0
    # The rich table wraps long cells, so assert on the stable title text.
    assert "local classification" in result.stdout


def test_classify_json_shape() -> None:
    result = runner.invoke(app, ["classify", str(FIXTURE), "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert any(row["label"] == "inline_no_definition" for row in payload)
    row = payload[0]
    assert "confidence" in row
    assert "recommended_actions" in row


def test_classify_label_filter() -> None:
    result = runner.invoke(
        app,
        ["classify", str(FIXTURE), "--format", "json", "--label-filter", "inline_no_definition"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload
    assert all(row["label"] == "inline_no_definition" for row in payload)


def test_classify_min_confidence_high() -> None:
    result = runner.invoke(
        app,
        ["classify", str(FIXTURE), "--format", "json", "--min-confidence", "high"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert all(row["confidence"] == "high" for row in payload)


def test_classify_bad_format() -> None:
    result = runner.invoke(app, ["classify", str(FIXTURE), "--format", "xml"])
    assert result.exit_code == 2


def test_rank_jsonl() -> None:
    result = runner.invoke(app, ["rank", str(FIXTURE), "--local", "--format", "jsonl"])
    assert result.exit_code == 0
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    first = json.loads(lines[0])
    assert first["rank"] == 1
    assert "score" in first
    assert "score_reasons" in first


def test_rank_markdown_heading() -> None:
    result = runner.invoke(app, ["rank", str(FIXTURE), "--format", "markdown"])
    assert result.exit_code == 0
    assert "# Ranked Compiler Optimization Findings" in result.stdout


def test_rank_top_limit(tmp_path: Path) -> None:
    out = tmp_path / "ranked.md"
    result = runner.invoke(
        app,
        ["rank", str(FIXTURE), "--top", "1", "--format", "markdown", "-o", str(out)],
    )
    assert result.exit_code == 0
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "## 1." in text
    assert "## 2." not in text


def test_rank_model_without_path_fails() -> None:
    result = runner.invoke(app, ["rank", str(FIXTURE), "--ranker", "model"])
    assert result.exit_code == 2


def test_rank_model_with_missing_model_fails_clearly() -> None:
    result = runner.invoke(
        app,
        ["rank", str(FIXTURE), "--ranker", "model", "--model-path", "/tmp/does-not-exist.bin"],
    )
    assert result.exit_code == 2
    assert "not implemented" in result.output or "model" in result.output


SIMD = Path(__file__).resolve().parent / "fixtures" / "simd_vectorized.opt.yaml"


def test_explain_local_is_evidence_first() -> None:
    result = runner.invoke(app, ["explain", str(SIMD), "--local"])
    assert result.exit_code == 0
    assert "Compiler evidence:" in result.stdout
    assert "Local diagnosis:" in result.stdout
    assert "Explanation:" in result.stdout
    assert "vectorize_success" in result.stdout


def test_explain_offline_forbids_openai_backend() -> None:
    result = runner.invoke(app, ["explain", str(SIMD), "--offline", "--backend", "openai"])
    assert result.exit_code == 2
    assert "offline" in result.output.lower()


def test_explain_no_network_forbids_ollama() -> None:
    result = runner.invoke(app, ["explain", str(SIMD), "--no-network", "--backend", "ollama"])
    assert result.exit_code == 2


def test_report_local_markdown_sections() -> None:
    result = runner.invoke(app, ["report", str(FIXTURE), "--local", "--format", "markdown"])
    assert result.exit_code == 0
    assert "## Summary" in result.stdout
    assert "## Top ranked findings" in result.stdout
    assert "## Local diagnosis summary by label" in result.stdout
    assert "## Recommended actions" in result.stdout


def test_report_local_json() -> None:
    result = runner.invoke(app, ["report", str(FIXTURE), "--local", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["total"] == 2
    assert "top_findings" in payload
    assert "by_label" in payload


def test_report_local_html_rejected() -> None:
    result = runner.invoke(app, ["report", str(FIXTURE), "--local", "--format", "html"])
    assert result.exit_code == 2


def test_report_offline_forbids_network_backend() -> None:
    result = runner.invoke(
        app,
        ["report", str(FIXTURE), "--offline", "--explain-backend", "claude"],
    )
    assert result.exit_code == 2
