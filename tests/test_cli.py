"""Smoke tests for the CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from explncc import __version__
from explncc.cli import app

runner = CliRunner()

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "inline_miss_no_definition.opt.yaml"
TINY = Path(__file__).resolve().parent / "fixtures" / "tiny_passed.opt.yaml"
FIXTURE_SIMD = Path(__file__).resolve().parent / "fixtures" / "simd_vectorized.opt.yaml"


def test_version_short_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_version_subcommand() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_help_no_subcommand() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "explncc" in result.stdout
    assert "version" in result.stdout
    assert "summary" in result.stdout
    assert "alignment" in result.stdout
    assert "report" in result.stdout
    assert "digest" in result.stdout
    assert "doctor" in result.stdout
    assert "viz" in result.stdout
    assert "evidence" in result.stdout


def test_digest_json_shape() -> None:
    result = runner.invoke(app, ["digest", str(FIXTURE)])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "cache_key" in data
    assert "files" in data
    assert data["file_count"] >= 1


def test_doctor_stdout_json() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "default_backend" in data
    assert data["openai_api_key"] in ("set", "unset")


def test_summary_json_contains_pass() -> None:
    result = runner.invoke(app, ["summary", str(FIXTURE), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data[0]["pass_name"] == "inline"


def test_stats_json_total() -> None:
    result = runner.invoke(app, ["stats", str(FIXTURE), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["total"] >= 2


def test_export_csv_stdout() -> None:
    result = runner.invoke(app, ["export", str(FIXTURE), "--format", "csv"])
    assert result.exit_code == 0
    assert "pass_name" in result.stdout


def test_diff_json_shape() -> None:
    result = runner.invoke(app, ["diff", str(FIXTURE), str(TINY), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "resolved_missed" in payload


def test_check_ok_with_loose_caps() -> None:
    result = runner.invoke(
        app,
        ["check", str(FIXTURE), "--max-missed-inline", "50", "--max-missed-loop-vectorize", "50"],
    )
    assert result.exit_code == 0


def test_check_fails_tight_inline() -> None:
    result = runner.invoke(app, ["check", str(FIXTURE), "--max-missed-inline", "0"])
    assert result.exit_code == 1


def test_explain_rule_backend() -> None:
    result = runner.invoke(
        app,
        ["explain", str(FIXTURE), "--backend", "rule", "--limit", "5"],
    )
    assert result.exit_code == 0
    assert "inliner" in result.stdout.lower() or "translation" in result.stdout.lower()


def test_explain_openai_without_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = runner.invoke(app, ["explain", str(FIXTURE), "--backend", "openai"])
    assert result.exit_code == 2


def test_alignment_json_includes_signals() -> None:
    result = runner.invoke(app, ["alignment", str(FIXTURE_SIMD), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data[0]["pass_name"] == "loop-vectorize"
    assert "alignment_signals" in data[0]
    assert data[0]["alignment_label"] == "alignment_plausible_not_proven"
    assert data[0]["alignment_confidence"] == "medium"
    assert "evidence_reasons" in data[0]
    assert "missing_context" in data[0]
    assert "recommended_next_steps" in data[0]


def test_alignment_pack_json(tmp_path: Path) -> None:
    out = tmp_path / "packs.jsonl"
    result = runner.invoke(
        app,
        [
            "alignment-pack",
            str(FIXTURE_SIMD),
            "--format",
            "jsonl",
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 0
    assert out.exists()
    row = json.loads(out.read_text(encoding="utf-8").strip())
    assert row["alignment_label"] == "alignment_plausible_not_proven"
    assert row["pack_id"]
    assert row["source_record_id"]
    assert row["raw_record_hash"]


def test_alignment_pack_unknown_label() -> None:
    result = runner.invoke(
        app,
        ["alignment-pack", str(FIXTURE_SIMD), "--label", "not_a_label"],
    )
    assert result.exit_code == 2


def test_alignment_pack_with_source_context(tmp_path: Path) -> None:
    fixtures = Path(__file__).resolve().parent / "fixtures"
    result = runner.invoke(
        app,
        [
            "alignment-pack",
            str(FIXTURE_SIMD),
            "--include-source",
            "--source-root",
            str(fixtures),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data[0]["source_snippet"] is not None
    assert "source_snippet" not in data[0]["missing_context"]


def test_dataset_writes_jsonl(tmp_path: Path) -> None:
    out = tmp_path / "train.jsonl"
    result = runner.invoke(
        app,
        [
            "dataset",
            str(FIXTURE_SIMD),
            "-o",
            str(out),
            "--focus",
            "all",
            "--format",
            "openai-messages",
            "--template",
            "minimal",
        ],
    )
    assert result.exit_code == 0
    assert out.is_file()
    assert '"messages"' in out.read_text(encoding="utf-8")


def test_dataset_alignment_focus_writes_labels(tmp_path: Path) -> None:
    out = tmp_path / "alignment.jsonl"
    result = runner.invoke(
        app,
        [
            "dataset",
            str(FIXTURE_SIMD),
            "-o",
            str(out),
            "--focus",
            "alignment",
            "--format",
            "explncc-record",
            "--template",
            "guided",
        ],
    )
    assert result.exit_code == 0
    row = json.loads(out.read_text(encoding="utf-8").strip())
    assert row["alignment_label"] == "alignment_plausible_not_proven"
    assert "teacher_response" in row
    assert "expected_behavior" in row
    assert row["evidence"]["pass_name"] == "loop-vectorize"


def test_evidence_json_stdout() -> None:
    result = runner.invoke(app, ["evidence", str(FIXTURE_SIMD), "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data) == 1
    assert data[0]["primary_pass"] == "loop-vectorize"
    assert "optimization_log_path" in data[0]


def test_evidence_kind_filter_jsonl() -> None:
    result = runner.invoke(
        app,
        ["evidence", str(FIXTURE), "--kind", "missed", "--format", "jsonl"],
    )
    assert result.exit_code == 0
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["primary_remark"] == "NoDefinition"


def test_evidence_bad_format() -> None:
    result = runner.invoke(app, ["evidence", str(TINY), "--format", "yaml"])
    assert result.exit_code == 2


def test_evidence_include_source_requires_source_root() -> None:
    result = runner.invoke(app, ["evidence", str(TINY), "--include-source"])
    assert result.exit_code == 2


def test_evidence_include_ir_requires_ir_file() -> None:
    result = runner.invoke(app, ["evidence", str(TINY), "--include-ir"])
    assert result.exit_code == 2


def test_evidence_output_file(tmp_path: Path) -> None:
    out = tmp_path / "evidence.json"
    result = runner.invoke(app, ["evidence", str(FIXTURE_SIMD), "-o", str(out)])
    assert result.exit_code == 0
    assert out.is_file()
    assert json.loads(out.read_text(encoding="utf-8"))[0]["pack_id"]


def test_bench_prompts_variants() -> None:
    result = runner.invoke(
        app,
        [
            "bench-prompts",
            str(FIXTURE_SIMD),
            "--focus",
            "all",
            "--templates",
            "minimal,rubric",
        ],
    )
    assert result.exit_code == 0
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert len(lines) == 2
