"""Chapter 12 CI feedback loop: report-diff, manifest, policy, explanation safety."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from explncc.checks import build_policy_result, run_checks
from explncc.ci_manifest import CiManifest, write_manifest
from explncc.cli import app
from explncc.models import OptimizationRecord
from explncc.report_diff import build_report_diff, render_report_diff
from explncc.report_helpers import resolve_explanation
from explncc.config import load_config

runner = CliRunner()
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "inline_miss_no_definition.opt.yaml"


def test_no_explain_default_cli() -> None:
    result = runner.invoke(app, ["report", str(FIXTURE), "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["explanations"]["enabled"] is False


def test_report_json_metadata_flags() -> None:
    result = runner.invoke(
        app,
        [
            "report",
            str(FIXTURE),
            "--format",
            "json",
            "--git-sha",
            "deadbeef",
            "--branch",
            "main",
            "--ci-provider",
            "github",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["metadata"]["git_sha"] == "deadbeef"
    assert data["metadata"]["branch"] == "main"
    assert data["metadata"]["pr_number"] is None


def test_report_markdown_github_smoke() -> None:
    for fmt in ("markdown", "github"):
        result = runner.invoke(
            app,
            ["report", str(FIXTURE), "--format", fmt, "--top-missed", "3"],
        )
        assert result.exit_code == 0
        assert "Compiler Optimization Report" in result.stdout


def test_report_fail_on_check_policy(tmp_path: Path) -> None:
    out = tmp_path / "gate.md"
    result = runner.invoke(
        app,
        [
            "report",
            str(FIXTURE),
            "--format",
            "markdown",
            "--fail-on-check",
            "--max-missed-inline",
            "0",
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 1
    assert out.is_file()


def test_max_missed_vectorize_and_total() -> None:
    recs = [
        OptimizationRecord(kind="missed", pass_name="loop-vectorize", remark_name="a"),
        OptimizationRecord(kind="missed", pass_name="inline", remark_name="b"),
    ]
    assert not run_checks(recs, max_missed_vectorize=0).ok
    assert not run_checks(recs, max_total_missed=1).ok
    assert run_checks(recs, max_total_missed=2).ok


def test_explain_only_on_failure_skips_when_pass() -> None:
    recs = [OptimizationRecord(kind="passed", pass_name="inline", remark_name="ok")]
    policy = build_policy_result(recs, max_missed_inline=100)
    info, code = resolve_explanation(
        recs,
        enabled=True,
        backend="rule",
        config=load_config(),
        explain_limit=5,
        ai_limit=5,
        only_on_failure=True,
        policy=policy,
        strict=False,
    )
    assert code is None
    assert not info.enabled


def test_backend_failure_fallback() -> None:
    recs = [OptimizationRecord(kind="missed", pass_name="inline", remark_name="x")]
    with patch("explncc.report_helpers.run_explanation", side_effect=RuntimeError("boom")):
        info, code = resolve_explanation(
            recs,
            enabled=True,
            backend="rule",
            config=load_config(),
            explain_limit=5,
            ai_limit=5,
            only_on_failure=False,
            policy=None,
            strict=False,
        )
    assert code is None
    assert info.warning is not None


def test_strict_explain_exits() -> None:
    recs = [OptimizationRecord(kind="missed", pass_name="inline", remark_name="x")]
    with patch("explncc.report_helpers.run_explanation", side_effect=RuntimeError("boom")):
        info, code = resolve_explanation(
            recs,
            enabled=True,
            backend="rule",
            config=load_config(),
            explain_limit=5,
            ai_limit=5,
            only_on_failure=False,
            policy=None,
            strict=True,
        )
    assert code == 1
    assert info.warning is not None


def test_report_diff_appeared_disappeared() -> None:
    before = [OptimizationRecord(kind="missed", pass_name="inline", remark_name="old", file="a.cpp", line=1)]
    after = [
        OptimizationRecord(kind="missed", pass_name="inline", remark_name="new", file="b.cpp", line=2),
    ]
    diff = build_report_diff(before, after, before_label="main", after_label="pr")
    types = {c.change_type for c in diff.changes}
    assert "new_missed" in types
    assert "resolved_missed" in types


def test_report_diff_vectorization_loss() -> None:
    before = [
        OptimizationRecord(
            kind="passed",
            pass_name="loop-vectorize",
            remark_name="vectorized",
            file="a.cpp",
            line=1,
            vectorization_factor=4,
        ),
    ]
    after = [
        OptimizationRecord(
            kind="missed",
            pass_name="loop-vectorize",
            remark_name="not vectorized",
            file="a.cpp",
            line=1,
        ),
    ]
    diff = build_report_diff(before, after)
    assert any(c.change_type in {"new_missed", "vectorization_lost"} for c in diff.changes)


def test_report_diff_cost_change() -> None:
    before = [
        OptimizationRecord(
            kind="analysis",
            pass_name="loop-vectorize",
            remark_name="cost",
            file="a.cpp",
            line=1,
            cost="scalar=10",
        ),
    ]
    after = [
        OptimizationRecord(
            kind="analysis",
            pass_name="loop-vectorize",
            remark_name="cost",
            file="a.cpp",
            line=1,
            cost="scalar=20",
        ),
    ]
    diff = build_report_diff(before, after)
    assert any(c.change_type == "cost_changed" for c in diff.changes)


def test_report_diff_github_output() -> None:
    before = [OptimizationRecord(kind="missed", pass_name="inline", remark_name="a", file="x.cpp", line=1)]
    after = [OptimizationRecord(kind="missed", pass_name="inline", remark_name="b", file="y.cpp", line=2)]
    diff = build_report_diff(before, after)
    text = render_report_diff("github", diff, top_changes=5)
    assert "<details>" in text
    assert "Semantic changes" in text


def test_report_diff_cli_smoke(tmp_path: Path) -> None:
    out = tmp_path / "diff.md"
    result = runner.invoke(
        app,
        [
            "report-diff",
            str(FIXTURE),
            str(FIXTURE),
            "--format",
            "markdown",
            "-o",
            str(out),
            "--before-label",
            "a",
            "--after-label",
            "b",
        ],
    )
    assert result.exit_code == 0
    assert out.is_file()


def test_ci_manifest_generation(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    manifest = CiManifest(
        git_sha="abc",
        markdown_report="report.md",
        raw_opt_yaml=["build/app.opt.yaml"],
    )
    write_manifest(str(path), manifest)
    data = json.loads(path.read_text())
    assert data["schema_version"] == "1.0"
    assert data["markdown_report"] == "report.md"
    assert data["git_sha"] == "abc"


def test_report_write_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    report = tmp_path / "report.json"
    result = runner.invoke(
        app,
        [
            "report",
            str(FIXTURE),
            "--format",
            "json",
            "-o",
            str(report),
            "--write-manifest",
            str(manifest),
            "--git-sha",
            "sha1",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(manifest.read_text())
    assert data["json_report"] == str(report)
    assert data["git_sha"] == "sha1"
