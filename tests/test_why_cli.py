"""CLI tests for ``explncc why`` (fused findings front door)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from explncc.cli import app

runner = CliRunner()

FUSION_DIR = Path(__file__).resolve().parent / "fixtures" / "fusion"
FIXTURE = FUSION_DIR / "hot.opt.yaml"


def test_why_renders_fused_finding_with_cause_and_suggestion() -> None:
    result = runner.invoke(app, ["why", str(FIXTURE)])
    assert result.exit_code == 0
    out = result.stdout
    assert "MISS  not vectorized: loop-carried dependence  [loop-vectorize, 2 records]" in out
    flat = " ".join(out.split())
    assert "Backward loop carried data dependence" in flat
    assert "suggest: Use #pragma clang loop distribute(enable)" in flat
    # The UnsafeDep analysis is folded into the miss, never shown as its own entry.
    assert "analysis: loop-vectorize/UnsafeDep" not in out


def test_why_shows_source_snippet_with_caret() -> None:
    result = runner.invoke(app, ["why", str(FIXTURE)])
    assert result.exit_code == 0
    assert "for (int i = 1; i < n; ++i) a[i] = a[i-1] + b[i];" in result.stdout
    caret_lines = [
        line for line in result.stdout.splitlines() if line.strip().startswith("|") and "^" in line
    ]
    assert caret_lines, "expected a caret line under the offending column"


def test_why_location_query_with_auto_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(FUSION_DIR)
    result = runner.invoke(app, ["why", "hot.cpp:11"])
    assert result.exit_code == 0
    assert "1 finding," in result.stdout
    assert "not vectorized: loop-carried dependence" in result.stdout
    assert "saxpy" not in result.stdout


def test_why_function_query_filters() -> None:
    result = runner.invoke(app, ["why", str(FIXTURE), "saxpy"])
    assert result.exit_code == 0
    assert "SLP not beneficial" in result.stdout
    assert "scan(" not in result.stdout


def test_why_missed_only_hides_positive_and_note_findings() -> None:
    result = runner.invoke(app, ["why", str(FIXTURE), "--missed-only"])
    assert result.exit_code == 0
    assert "OK  vectorized" not in result.stdout
    # regalloc spills arrive as !Missed records but are NOTE-tier, not misses.
    assert "register spill" not in result.stdout
    assert "MISS" in result.stdout


def test_why_all_includes_noise() -> None:
    quiet = runner.invoke(app, ["why", str(FIXTURE)])
    noisy = runner.invoke(app, ["why", str(FIXTURE), "--all", "--top", "0"])
    assert quiet.exit_code == noisy.exit_code == 0
    assert "asm-printer" not in quiet.stdout
    assert "asm-printer" in noisy.stdout


def test_why_top_truncates_with_footer() -> None:
    result = runner.invoke(app, ["why", str(FIXTURE), "--top", "2"])
    assert result.exit_code == 0
    assert "more finding(s); use --top 0 to show everything" in result.stdout


def test_why_no_match_reports_total() -> None:
    result = runner.invoke(app, ["why", str(FIXTURE), "definitely_not_a_function"])
    assert result.exit_code == 0
    assert "no findings matching" in result.stdout


def test_why_without_records_explains_how_to_generate_them(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["why", "foo.cpp:3"])
    assert result.exit_code == 2
    err = result.output
    assert "-fsave-optimization-record" in err


def test_why_rejects_unrecognizable_target(tmp_path: Path) -> None:
    bogus = tmp_path / "notes.txt"
    bogus.write_text("hello", encoding="utf-8")
    result = runner.invoke(app, ["why", str(bogus)])
    assert result.exit_code == 2


def test_why_output_is_deterministic_and_dash_clean() -> None:
    a = runner.invoke(app, ["why", str(FIXTURE), "--top", "0"])
    b = runner.invoke(app, ["why", str(FIXTURE), "--top", "0"])
    assert a.stdout == b.stdout
    assert "—" not in a.stdout  # em dash
    assert "–" not in a.stdout  # en dash
