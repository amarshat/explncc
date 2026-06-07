"""Tests for the experimental HLS (high-level-synthesis) report adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from explncc.explain.rule_based import build_rule_explanation
from explncc.records_loader import load_records
from explncc.toolchains import get_adapter
from explncc.toolchains.hls import parse_csynth_xml

FIXTURES = Path(__file__).parent / "fixtures" / "hls"


def test_adapter_registered() -> None:
    adapter = get_adapter("hls")
    assert adapter.name == "hls"
    assert ".xml" in adapter.supported_file_extensions()


def test_pipelined_good_is_passed() -> None:
    records = load_records(FIXTURES / "pipelined_good.xml", toolchain="hls")
    assert len(records) == 1
    r = records[0]
    assert r.kind == "passed"
    assert r.pass_name == "hls-pipeline"
    assert r.remark_name == "Pipelined"
    assert r.initiation_interval == 1
    assert r.target_ii == 1
    assert r.cost == "1"
    assert r.threshold == "1"
    assert r.function == "fir_filter"


def test_ii_not_achieved_is_missed_with_gap() -> None:
    records = load_records(FIXTURES / "ii_not_achieved.xml", toolchain="hls")
    assert len(records) == 1
    r = records[0]
    assert r.kind == "missed"
    assert r.remark_name == "IINotAchieved"
    assert r.initiation_interval == 3
    assert r.target_ii == 1
    assert "carried dependency" in (r.message or "")
    assert r.trip_count == 1024


def test_not_pipelined_is_missed() -> None:
    records = load_records(FIXTURES / "not_pipelined.xml", toolchain="hls")
    assert len(records) == 1
    r = records[0]
    assert r.kind == "missed"
    assert r.remark_name == "LoopNotPipelined"
    assert r.initiation_interval is None


def test_directory_discovery_collects_all_reports() -> None:
    records = load_records(FIXTURES, toolchain="hls")
    remark_names = {r.remark_name for r in records}
    # diff_before/diff_after also contribute IINotAchieved / Pipelined.
    assert {"Pipelined", "IINotAchieved", "LoopNotPipelined"} <= remark_names


def test_identity_fields_are_populated() -> None:
    r = load_records(FIXTURES / "ii_not_achieved.xml", toolchain="hls")[0]
    assert r.record_id and r.record_id.startswith("hls-pipeline/missed/IINotAchieved/")
    assert r.record_hash and len(r.record_hash) == 64
    assert r.semantic_key and "hls-pipeline" in r.semantic_key


def test_diff_pair_resolves_ii_regression() -> None:
    before = load_records(FIXTURES / "diff_before" / "accumulate.xml", toolchain="hls")
    after = load_records(FIXTURES / "diff_after" / "accumulate.xml", toolchain="hls")
    from explncc.diffing import diff_records

    report = diff_records(before, after)
    assert len(report.new_missed) == 0
    assert len(report.resolved_missed) == 1
    assert report.resolved_missed[0].remark_name == "IINotAchieved"


def test_rule_explanation_grounds_hls_ii() -> None:
    records = load_records(FIXTURES / "ii_not_achieved.xml", toolchain="hls")
    text = build_rule_explanation(records)
    assert "initiation interval" in text.lower()
    assert "II=3" in text or "II=1" in text
    assert "dependency" in text.lower()


def test_clang_path_unaffected() -> None:
    """The default Clang adapter still loads .opt.yaml fixtures unchanged."""
    clang_fixture = Path(__file__).parent / "fixtures" / "simd_vectorized.opt.yaml"
    records = load_records(clang_fixture, toolchain="clang")
    assert records
    assert all(r.pass_name != "hls-pipeline" for r in records)


def test_bad_xml_raises_valueerror() -> None:
    with pytest.raises(ValueError):
        parse_csynth_xml("<not-valid-xml", source_path=None)


# --- CI commands accept --toolchain hls (Chapter 12) ---

from typer.testing import CliRunner  # noqa: E402

from explncc.cli import app  # noqa: E402

_RUNNER = CliRunner()


def test_report_cli_toolchain_hls() -> None:
    result = _RUNNER.invoke(
        app,
        ["report", str(FIXTURES / "ii_not_achieved.xml"), "--toolchain", "hls",
         "--format", "markdown", "--no-explain"],
    )
    assert result.exit_code == 0
    assert "hls-pipeline" in result.stdout
    assert "IINotAchieved" in result.stdout


def test_report_cli_hls_gate_fails() -> None:
    result = _RUNNER.invoke(
        app,
        ["report", str(FIXTURES / "ii_not_achieved.xml"), "--toolchain", "hls",
         "--format", "markdown", "--no-explain", "--fail-on-check", "--max-total-missed", "0"],
    )
    assert result.exit_code == 1
    assert "fail" in result.stdout.lower()


def test_check_cli_toolchain_hls_loads_records() -> None:
    # A clean pipelined report has no misses, so the gate passes (exit 0).
    result = _RUNNER.invoke(
        app,
        ["check", str(FIXTURES / "pipelined_good.xml"), "--toolchain", "hls",
         "--max-missed-loop-vectorize", "0"],
    )
    assert result.exit_code == 0


def test_report_diff_cli_toolchain_hls() -> None:
    result = _RUNNER.invoke(
        app,
        ["report-diff", str(FIXTURES / "diff_before" / "accumulate.xml"),
         str(FIXTURES / "diff_after" / "accumulate.xml"), "--toolchain", "hls",
         "--format", "markdown"],
    )
    assert result.exit_code == 0
    assert "IINotAchieved" in result.stdout
